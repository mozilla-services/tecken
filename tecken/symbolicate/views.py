# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import time
import logging
from bisect import bisect
from collections import defaultdict

import ujson as json

import requests
from django_redis import get_redis_connection

from django.conf import settings
from django.http import HttpResponse
from django.core.cache import cache, caches
from django.views.decorators.csrf import csrf_exempt
from django.template.defaultfilters import filesizeformat

logger = logging.getLogger('django')
store = caches['store']


class SymbolDownloadError(Exception):
    def __init__(self, status_code, url):
        self.status_code = status_code
        self.url = url


class SymbolNotFound(Exception):
    """Happens when you try to download a symbols file that doesn't exist"""


class SymbolFileEmpty(Exception):
    """Happens when we 200 OK download a file that exists but is
    entirely empty."""


class LogCacheHitsMixin:
    """Mixing for storing information about cache hits and misses.

    In production, this caching is set to NOT timeout.
    That makes it possible to get an insight into cache hits/misses over
    time.
    """

    log_cache_timeout = settings.DEBUG and 60 * 60 * 24 or None

    def log_symbol_cache_miss(self, cache_key):
        # This uses memcache
        if cache.get(cache_key):
            # oh my! The symbol was previously a hit
            self.log_symbol_cache_evicted(cache_key)
        cache.set(cache_key, 0, timeout=self.log_cache_timeout)

    def log_symbol_cache_evicted(self, cache_key):
        self.log_symbol_cache_hit(cache_key + ':evicted')

    def log_symbol_cache_hit(self, cache_key):
        try:
            cache.incr(cache_key)
        except ValueError:
            # If it wasn't in cache we can't increment this
            # hit, so we have to start from 1.
            cache.set(cache_key, 1, timeout=self.log_cache_timeout)


class JsonResponse(HttpResponse):
    """
    An "overwrite" of django.http.JsonResponse that uses "our"
    imported json instead which can be ujson.
    The only difference is that it never tries to be smart about
    sending in an encoder to take care of tricky types like
    Decimals and datetime objects.
    """

    def __init__(self, data, safe=True,
                 json_dumps_params=None, **kwargs):
        if safe and not isinstance(data, dict):
            raise TypeError(
                'In order to allow non-dict objects to be serialized set the '
                'safe parameter to False.'
            )
        if json_dumps_params is None:
            json_dumps_params = {}
        kwargs.setdefault('content_type', 'application/json')
        data = json.dumps(data, **json_dumps_params)
        super().__init__(content=data, **kwargs)


class SymbolicateJSON(LogCacheHitsMixin):
    def __init__(self, stacks, memory_map, debug=False):
        self.stacks = stacks
        self.memory_map = memory_map
        self.debug = debug
        self.session = requests.Session()
        # per request global map of all symbol maps
        self.all_symbol_maps = {}
        # the result we will populate
        self.result = {
            'symbolicatedStacks': [],
            'knownModules': [False] * len(memory_map),
        }
        self._run()

    def add_to_symbols_maps(self, key, map_):
        # When inserting to the function global all_symbol_maps
        # store it as a tuple with an additional value (for
        # the sake of optimization) of the sorted list of ALL
        # offsets as int16s ascending order.
        self.all_symbol_maps[key] = (
            map_,
            sorted(map_)
        )

    def _run(self):
        # Record the total time it took to symbolicate
        t0 = time.time()

        cache_lookup_times = []
        cache_lookup_sizes = []
        download_times = []
        download_sizes = []
        modules_lookups = set()

        # First look up all symbols that we're going to need so that
        # when it's time to really loop over `self.stacks` the
        # 'self.all_symbol_maps' should be fully populated as well as it
        # can be.
        needs_to_be_downloaded = set()
        for stack in self.stacks:
            for module_index, module_offset in stack:
                if module_index < 0:
                    continue
                filename, debug_id = self.memory_map[module_index]
                symbol_key = (filename, debug_id)
                modules_lookups.add(symbol_key)
                information = self.get_symbol_map(symbol_key)
                # Hit or miss, there was a cache lookup
                if self.debug:
                    cache_lookup_times.append(
                        information['cache_lookup_time']
                    )
                    # If it was a misse, there'd be no size
                    if 'cache_lookup_size' in information:
                        cache_lookup_sizes.append(
                            information['cache_lookup_size']
                        )
                if 'symbol_map' in information:
                    # We were able to look it up from cache.
                    symbol_map = information['symbol_map']
                    # But even though it was in cache it might have just
                    # been cached temporarily because it has previously
                    # failed.
                    found = information['found']

                    # If it was successfully fetched from cache,
                    # these metrics will be available.
                    self.result['knownModules'][module_index] = found
                    self.add_to_symbols_maps(symbol_key, symbol_map)
                else:
                    needs_to_be_downloaded.add((
                        symbol_key,
                        module_index
                    ))

        # Now let's go ahead and download the symbols that need to be
        # fetched over the network.
        downloaded = self.load_symbols(needs_to_be_downloaded)
        for symbol_key, information, module_index in downloaded:
            symbol_map = information['symbol_map']
            self.add_to_symbols_maps(symbol_key, symbol_map)
            if self.debug:
                if 'download_time' in information:
                    download_times.append(information['download_time'])
                if 'download_size' in information:
                    download_sizes.append(information['download_size'])
            found = information['found']
            self.result['knownModules'][module_index] = found

        total_stacks = 0
        real_stacks = 0

        stacks_per_module = defaultdict(int)

        # Now that all needed symbols are looked up, we should be
        # ready to symbolicate for reals.
        for i, stack in enumerate(self.stacks):
            response_stack = []
            for j, (module_index, module_offset) in enumerate(stack):
                total_stacks += 1
                if module_index < 0:
                    try:
                        response_stack.append(hex(module_offset))
                    except TypeError:
                        logger.warning('TypeError on ({!r}, {!r})'.format(
                            module_offset,
                            module_index,
                        ))
                        # Happens if 'module_offset' is not an int16
                        # and thus can't be represented in hex.
                        response_stack.append(str(module_offset))
                    continue

                real_stacks += 1

                symbol_filename, debug_id = self.memory_map[module_index]

                symbol_key = (symbol_filename, debug_id)

                # This 'stacks_per_module' will only be used in the debug
                # output. So give it a string key instead of a tuple.
                stacks_per_module['{}/{}'.format(*symbol_key)] += 1

                symbol_map, symbol_offset_list = self.all_symbol_maps.get(
                    symbol_key,
                    ({}, [])
                )
                signature = symbol_map.get(module_offset)
                if signature is None and symbol_map:
                    signature = symbol_map[
                        symbol_offset_list[
                            bisect(symbol_offset_list, module_offset) - 1
                        ]
                    ]

                response_stack.append(
                    '{} (in {})'.format(
                        signature or hex(module_offset),
                        symbol_filename
                    )
                )
            self.result['symbolicatedStacks'].append(response_stack)

        t1 = time.time()

        logger.info(
            'The whole symbolication of {} ({} actual) '
            'stacks took {:.4f} seconds'.format(
                total_stacks,
                real_stacks,
                t1 - t0,
            )
        )

        if self.debug:
            self.result['debug'] = {
                'time': t1 - t0,
                'stacks': {
                    'count': total_stacks,
                    'real': real_stacks,
                },
                'modules': {
                    'count': len(modules_lookups),
                    'stacks_per_module': stacks_per_module,
                },
                'cache_lookups': {
                    'count': len(cache_lookup_times),
                    'time': float(sum(cache_lookup_times)),
                    'size': float(sum(cache_lookup_sizes)),
                },
                'downloads': {
                    'count': len(download_times),
                    'time': float(sum(download_times)),
                    'size': float(sum(download_sizes)),
                }
            }

    @staticmethod
    def _make_cache_key(symbol_key):
        return 'symbol:{}/{}'.format(*symbol_key)

    def get_symbol_map(self, symbol_key):
        cache_key = self._make_cache_key(symbol_key)
        information = {}
        t0 = time.time()
        symbol_map = store.get(cache_key)
        t1 = time.time()
        if self.debug:
            information['cache_lookup_time'] = t1 - t0

        if symbol_map is None:  # not existant in ccache
            # Need to download this from the Internet.
            self.log_symbol_cache_miss(cache_key)
            # If the symbols weren't in the cache, this will be dealt
            # with later by this method's caller.
        else:
            assert isinstance(symbol_map, dict)
            if not symbol_map:
                # It was cached but empty. That means it was logged that
                # it was previously attempted but failed.
                # The reason it's cached is to avoid it being looked up
                # again and again when it's just going to continue to fail.
                information['symbol_map'] = {}
                information['found'] = False
            else:
                if self.debug:
                    information['cache_lookup_size'] = len(
                        json.dumps(symbol_map)
                    )
                self.log_symbol_cache_hit(cache_key)
                # If it was in cache, that means it was originally found.
                information['symbol_map'] = symbol_map
                information['found'] = True

        return information

    def load_symbols(self, requirements):
        """return an iterator that yields 3-tuples of
        (symbol_key, information, module_index)
        """
        # XXX This could/should be done concurrently
        for symbol_key, module_index in requirements:
            cache_key = self._make_cache_key(symbol_key)
            information = {}
            try:
                information.update(self.load_symbol(*symbol_key))
                if not information['download_size']:
                    raise SymbolFileEmpty()
                assert isinstance(information['symbol_map'], dict)
                store.set(
                    cache_key,
                    information['symbol_map'],
                    # When doing local dev, only store it for 100 min
                    # But in prod set it to indefinite.
                    timeout=settings.DEBUG and 60 * 100 or None
                )
                logger.info(
                    'Storing {!r} ({}) in LRU cache (Took {:.2f}s)'.format(
                        cache_key,
                        filesizeformat(
                            len(json.dumps(information['symbol_map']))
                        ),
                        information['download_time'],
                    )
                )
                information['found'] = True
            except (SymbolNotFound, SymbolFileEmpty, SymbolDownloadError):
                # If it can't be downloaded, cache it as an empty result
                # so we don't need to do this every time we're asked to
                # look up this symbol.
                store.set(
                    cache_key,
                    {},
                    settings.DEBUG and 60 or 60 * 60,
                )
                # If nothing could be downloaded, keep it anyway but
                # to avoid having to check if 'symbol_map' is None, just
                # turn it into a dict.
                information['symbol_map'] = {}  # override
                information['found'] = False
            yield (symbol_key, information, module_index)

    def load_symbol(self, filename, debug_id):
        t0 = time.time()
        stream = self.get_download_symbol_stream(filename, debug_id)

        # Need to parse it by line and make a dict of of offset->function
        public_symbols = {}
        func_symbols = {}
        line_number = 0
        total_size = 0
        t0 = time.time()
        for line, url in stream:
            total_size += len(line)
            line_number += 1
            if line.startswith('PUBLIC '):
                fields = line.strip().split(None, 3)
                if len(fields) < 4:
                    logger.warning(
                        'PUBLIC line {} in {} has too few fields'.format(
                            line_number,
                            url,
                        )
                    )
                    continue
                address = int(fields[1], 16)
                symbol = fields[3]
                public_symbols[address] = symbol
            elif line.startswith('FUNC '):
                fields = line.strip().split(None, 4)
                if len(fields) < 4:
                    logger.warning(
                        'FUNC line {} in {} has too few fields'.format(
                            line_number,
                            url,
                        )
                    )
                    continue
                address = int(fields[1], 16)
                symbol = fields[4]
                func_symbols[address] = symbol

        # Prioritize PUBLIC symbols over FUNC symbols # XXX why?
        func_symbols.update(public_symbols)
        t1 = time.time()
        if not total_size:
            logger.warning('Downloaded content empty ({!r}, {!r})'.format(
                filename,
                debug_id,
            ))
        information = {}
        information['symbol_map'] = func_symbols
        information['download_time'] = t1 - t0
        information['download_size'] = total_size
        return information

    def get_download_symbol_stream(self, lib_filename, debug_id):
        """
        return a requests.response stream
        """
        if lib_filename.endswith('.pdb'):
            symbol_filename = lib_filename[:-4] + '.sym'
        else:
            symbol_filename = lib_filename + '.sym'

        requests_operational_errors = (
            requests.exceptions.ContentDecodingError,
            requests.exceptions.ReadTimeout,
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
        )

        for base_url in settings.SYMBOL_URLS:
            assert base_url.endswith('/')
            url = '{}{}/{}/{}'.format(
                base_url,
                lib_filename,
                debug_id,
                symbol_filename
            )
            logger.info('Requesting {}'.format(url))
            try:
                response = self.session.get(
                    url,
                    timeout=settings.SYMBOLS_GET_TIMEOUT
                )
            except requests_operational_errors as exception:
                logger.warning(
                    '{} when downloading {}'.format(
                        exception,
                        url,
                    )
                )
                continue
            if response.status_code == 404:
                logger.warning('{} 404 Not Found'.format(url))
                raise SymbolNotFound(url)
            if response.status_code == 200:  # Note! This includes redirects
                # Files downloaded from S3 should be UTF-8 but it's unlikely
                # that S3 exposes this in a header.
                # If the Content-Type in 'text/plain' requests will assume
                # the ISO-8859-1 encoding (this is according to RFC 2616).
                # But if the content type is 'binary/octet-stream' it can't
                # assume any encoding so it will be returned as a bytestring.
                if not response.encoding:
                    response.encoding = 'utf-8'
                for line in response.iter_lines(decode_unicode=True):
                    # filter out keep-alive newlines
                    if line:
                        yield line, url
                return url
            else:
                logger.warning('{} {} ({})'.format(
                    url,
                    response.status_code,
                    response.content,
                ))
                raise SymbolDownloadError(response.status_code, url)

        # None of the URLs worked


@csrf_exempt
def symbolicate_json(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Must use HTTP POST'}, status=405)
    try:
        json_body = json.loads(request.body.decode('utf-8'))
        if not isinstance(json_body, dict):
            return JsonResponse({'error': 'Not a dict'}, status=400)
    except ValueError as exception:
        return JsonResponse({'error': 'Invalid JSON passed in'}, status=400)

    try:
        stacks = json_body['stacks']
        memory_map = json_body['memoryMap']
        if json_body.get('version') != 4:
            return JsonResponse({'error': 'Expect version==4'}, status=400)
    except KeyError as exception:
        return JsonResponse({'error': 'Missing key JSON "{}"'.format(
            exception
        )}, status=400)

    symbolicator = SymbolicateJSON(
        stacks,
        memory_map,
        debug=json_body.get('debug')
    )
    return JsonResponse(symbolicator.result)


def metrics(request):
    cache_misses = []
    cache_hits = {}
    cache_evictions = {}
    count_keys = 0
    for key in store.iter_keys('symbol:*'):
        count = cache.get(key)
        if count is None:
            # It was cached in the redis-store before we started logging
            # hits in the redis-cache.
            continue
        count_keys += 1
        if count > 0:
            cache_hits[key] = count
        else:
            cache_misses.append(key)
        evicted_count = cache.get(key + ':evicted')
        if evicted_count:
            cache_evictions[key] = evicted_count

    sum_hits = sum(cache_hits.values())
    sum_misses = len(cache_misses)
    sum_evictions = sum(cache_evictions.values())

    context = {}
    context['keys'] = count_keys
    context['hits'] = sum_hits
    context['misses'] = sum_misses
    context['evictions'] = sum_evictions
    if sum_hits or sum_misses:
        context['ratio_of_hits'] = sum_hits / (sum_hits + sum_misses)
        context['percent_of_hits'] = 100 * context['ratio_of_hits']

    redis_store_connection = get_redis_connection('store')
    info = redis_store_connection.info()

    context['maxmemory'] = {
        'bytes': info['maxmemory'],
        'human': info['maxmemory_human'],
    }
    context['used_memory'] = {
        'bytes': info['used_memory'],
        'human': info['used_memory_human'],
        'ratio': info['used_memory'] / info['maxmemory'],
        'percent': 100 * info['used_memory'] / info['maxmemory'],
    }
    return JsonResponse(context)
