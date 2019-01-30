# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import time
import logging
from bisect import bisect
from functools import wraps
from collections import defaultdict

import markus
import ujson as json
import requests
import botocore

from django_redis import get_redis_connection

from django import http
from django.conf import settings
from django.http import HttpResponse
from django.core.cache import caches, cache
from django.views.decorators.csrf import csrf_exempt

from tecken.base.symboldownloader import SymbolDownloader, SymbolNotFound
from tecken.base.decorators import set_request_debug, set_cors_headers
from .utils import make_symbol_key_cache_key


logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")
store = caches["store"]

downloader = SymbolDownloader(
    settings.SYMBOL_URLS + [settings.UPLOAD_TRY_SYMBOLS_URL],
    file_prefix=settings.SYMBOL_FILE_PREFIX,
)

# The way Firefox serializes its CombinedStacks object, a negative module index
# indicates that the stack frame's program counter was not found in any known
# module. In this case, no symbolication occurs, but we support this case as a
# convenience so clients don't need to filter this case out of stack frames and
# re-add them after symbolication.
#
# We don't return a null module name in order to further simplify the logic for
# clients. By always returning a valid module name string, clients aren't forced
# to always check for this condition.
#
# Angle brackets '<' and '>' cannot appear in real module names, so clients can
# test for this string to detect this condition 100% reliably.
UNKNOWN_MODULE = "<unknown>"

# This lists all the possible exceptions that the SymbolDownloader
# might raise that we swallow in runtime.
# Any failure to download a symbol from S3, that is considered operational,
# does not need to be "bubbled up" to Sentry but should be used to
# terminate the symbolication request and return a 503 error.
operational_exceptions = (
    requests.exceptions.ReadTimeout,
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    botocore.exceptions.ConnectionError,
)


class SymbolFileEmpty(Exception):
    """Happens when we 200 OK download a file that exists but is
    entirely empty."""


class JsonResponse(HttpResponse):
    """
    An "overwrite" of django.http.JsonResponse that uses "our"
    imported json instead which can be ujson.
    The only difference is that it never tries to be smart about
    sending in an encoder to take care of tricky types like
    Decimals and datetime objects.
    """

    def __init__(self, data, safe=True, json_dumps_params=None, **kwargs):
        if safe and not isinstance(data, dict):
            raise TypeError(
                "In order to allow non-dict objects to be serialized set the "
                "safe parameter to False."
            )
        if json_dumps_params is None:
            json_dumps_params = {}
        kwargs.setdefault("content_type", "application/json")
        data = json.dumps(data, **json_dumps_params)
        super().__init__(content=data, **kwargs)


def get_symbolication_count_key(prefix, dateobj):
    date = dateobj.strftime("%Y%m%d")
    return f"symbolicationcount:{prefix}:{date}"


def increment_symbolication_count(prefix):
    cache_key = get_symbolication_count_key(prefix, datetime.datetime.utcnow())
    try:
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, 60 * 60 * 24 * 3)


class SymbolicateJSON:
    def __init__(self, downloader, debug=False):
        self.downloader = downloader
        self.debug = debug

        # These dicts fill up as we either query the Redis store or
        # download from S3.
        # By keeping them as class instance attributes, they stay
        # around between multiple symbolication requests.
        self.all_symbol_offsets = {}
        self.all_symbol_maps = {}

    def add_to_symbols_offsets(self, key, offsets, symbol_map=None):
        self.all_symbol_offsets[key] = sorted(offsets)

        # IF we had to download the symbol file, and parse it, let's
        # keep it around. This is an optimization technique.
        # Normally, a download from the Internet results in us stuffing
        # the Redis store with with all its values, then we actually
        # doing the symbolication process we query the Redis store for
        # each symbol key and offset. But if we already have it all
        # here in memory (because of the download), let's keep it and
        # save some Redis store queries.
        if symbol_map:
            self.all_symbol_maps[key] = symbol_map

    def symbolicate(self, stacks, memory_map):
        # the result we will populate
        result = {"symbolicatedStacks": [], "knownModules": [None] * len(memory_map)}

        # Record the total time it took to symbolicate
        t0 = time.time()

        cache_lookup_times = []
        download_times = []
        download_sizes = []
        modules_lookups = {}

        # First look up all symbols that we're going to need so that
        # when it's time to really loop over `self.stacks` the
        # 'self.all_symbol_offsets' should be fully populated as well as it
        # can be.
        needs_to_be_downloaded = set()
        for stack in stacks:
            for module_index, module_offset in stack:
                if module_index < 0:
                    continue
                filename, debug_id = memory_map[module_index]
                symbol_key = (filename, debug_id)
                # Keep a dict of the symbol keys and each's module index
                modules_lookups[symbol_key] = module_index

        # get_symbol_offsets() takes a list of symbol keys, returns a
        # dict that contains a dict called 'symbols'. Each key, in it,
        # is the symbol key and the values is the complete list of
        # ALL keys we have for that symbol key.
        # E.g. `informations['symbols'][('xul.pdb', 'HEX')] == [45110, 130109]`
        # If, for a particular symbol key we didn't have anything in the
        # Redis store, the value is None.
        needed_modules_lookups = {
            key: modules_lookups[key]
            for key in modules_lookups
            if key not in self.all_symbol_offsets
        }

        if needed_modules_lookups:
            informations = self.get_symbol_offsets(needed_modules_lookups)

            # Hit or miss, there was a cache (Redis store) lookup.
            if self.debug:
                cache_lookup_times.extend(informations["cache_lookup_times"])

            # Now loop over every symbol looked up from get_symbol_offsets()
            # Expect that, for every symbol, there is something. Even
            # though it might be empty. If it's empty (i.e. no 'symbol_map'
            # key) it means we looked in the cache but it not in the cache.
            for symbol_key in informations["symbols"]:
                module_index = modules_lookups[symbol_key]
                information = informations["symbols"][symbol_key]
                if "symbol_offsets" in information:
                    # We were able to look it up from cache.
                    symbol_offsets = information["symbol_offsets"]
                    # But even though it was in cache it might have just
                    # been cached temporarily because it has previously
                    # failed.
                    found = information["found"]

                    # If it was successfully fetched from cache,
                    # these metrics will be available.
                    result["knownModules"][module_index] = found
                    self.add_to_symbols_offsets(symbol_key, symbol_offsets)
                else:
                    # These are the symbols that we're going to have to
                    # download from the Internet.
                    needs_to_be_downloaded.add((symbol_key, module_index))

            # Now let's go ahead and download the symbols that need to be
            # fetch from the Internet.
            if needs_to_be_downloaded:
                # The self.load_symbols() method can cope
                # with 'needs_to_be_downloaded' being an empty list, as
                # there is simply nothing to do.
                # But we avoid the call since it has a timer on it. Otherwise
                # we get many timer timings that are unrealistically small
                # which makes it hard to see how long it takes.
                downloaded = self.load_symbols(needs_to_be_downloaded)
                for symbol_key, information, module_index in downloaded:
                    symbol_offsets = information["symbol_map"].keys()
                    self.add_to_symbols_offsets(
                        symbol_key, symbol_offsets, symbol_map=information["symbol_map"]
                    )
                    if self.debug:
                        if "download_time" in information:
                            download_times.append(information["download_time"])
                        if "download_size" in information:
                            download_sizes.append(information["download_size"])
                    found = information["found"]
                    result["knownModules"][module_index] = found

        # Initialize counters of how many stacks we do symbolication on.
        # Some stacks are malformed so we can't symbolicate them
        # so we keep a seperation between "total" and "real". Always
        # expect real_stacks <= total_stacks.
        total_stacks = 0
        real_stacks = 0

        # This counter is for the sake of the debug output. So you can
        # get an appreciation how much was needed from each module (aka
        # symbol).
        stacks_per_module = defaultdict(int)

        # Before we loop over the stack, loop over it once just to
        # figure out which HGET commands we're going to need to send.
        lookups = defaultdict(list)

        # We'll use the module_index repeatedly to figure out what the
        # of all symbol offsets are. To avoid repeating that logic
        # too much we'll just a little dict as a cache.
        _symbol_offset_list_cache = {}

        for stack in stacks:
            for module_index, module_offset in stack:
                if module_index < 0:
                    continue
                symbol_offset_list = _symbol_offset_list_cache.get(module_index)

                # First time we encounter this module_index?
                if symbol_offset_list is None:
                    symbol_filename, debug_id = memory_map[module_index]
                    symbol_key = (symbol_filename, debug_id)

                    symbol_offset_list = self.all_symbol_offsets.get(symbol_key)
                    _symbol_offset_list_cache[module_index] = symbol_offset_list

                if symbol_offset_list:
                    # There exists a list of offsets for this module!

                    symbol_key = tuple(memory_map[module_index])
                    nearest = self._get_nearest(symbol_offset_list, module_offset)
                    if nearest not in lookups[symbol_key]:
                        lookups[symbol_key].append(nearest)

        # Now we know which lookups we need to do. I.e. Redis store queries.
        # Actually look them up.
        signatures = {}
        redis_store_connection = get_redis_connection("store")

        for symbol_key, keys in lookups.items():
            signatures[symbol_key] = {}
            if symbol_key in self.all_symbol_maps:
                # 'all_symbol_maps' is a dict of *every* offset and signature
                # for this symbol key.
                # The reason we have this (and thus won't need to query Redis)
                # is because the symbol has had to be downloaded from the
                # Internet and parsed into a dict (for the sake of
                # storing it in Redis) already. Let's not waste this
                # opportunity. Basically only possible the first time you
                # depend on a module for symbolication.
                for key in keys:
                    signatures[symbol_key][key] = self.all_symbol_maps[symbol_key][key]
            else:
                cache_key = self._make_cache_key(symbol_key)
                t0 = time.time()
                values = redis_store_connection.hmget(store.make_key(cache_key), keys)
                t1 = time.time()
                cache_lookup_times.append(t1 - t0)

                for i, key in enumerate(keys):
                    # The list 'values' is a list of byte strings.
                    value = values[i]
                    if value is not None:
                        value = value.decode("utf-8")
                    signatures[symbol_key][key] = value

        _symbol_offset_list_cache = {}  # reset the cache

        # All the downloads (if there were any) *and* all the Redis store
        # lookups have been done. Now, let's focus on making the struct
        # that is going to be the output.
        for stack in stacks:
            response_stack = []
            for j, (module_index, module_offset) in enumerate(stack):
                total_stacks += 1
                if module_index < 0:
                    # Exit early. See declaration of UNKNOWN_MODULE for details
                    # about this case.
                    response_stack.append(
                        {
                            "module_offset": module_offset,
                            "module": UNKNOWN_MODULE,
                            "frame": j,
                        }
                    )
                    continue

                real_stacks += 1

                symbol_filename, debug_id = memory_map[module_index]

                symbol_offset_list = _symbol_offset_list_cache.get(module_index)
                if symbol_offset_list is None:
                    symbol_key = (symbol_filename, debug_id)

                    # This 'stacks_per_module' will only be used in the debug
                    # output. So give it a string key instead of a tuple.
                    stacks_per_module["{}/{}".format(*symbol_key)] += 1

                    symbol_offset_list = self.all_symbol_offsets.get(symbol_key)
                    _symbol_offset_list_cache[module_index] = symbol_offset_list

                # If there was no list, the symbol could ultimately not
                # be found, at all. There's no point trying to figure out
                # what the signature is.
                function = None
                if symbol_offset_list:
                    symbol_key = tuple(memory_map[module_index])
                    # Even if our module offset isn't in that list,
                    # there is still hope to be able to find the
                    # nearest signature.
                    function_start = self._get_nearest(
                        symbol_offset_list, module_offset
                    )
                    function_offset = module_offset - function_start
                    function = signatures[symbol_key][function_start]

                frame = {
                    "module_offset": module_offset,
                    "module": symbol_filename,
                    "frame": j,
                }
                if function is not None:
                    frame["function"] = function
                    frame["function_offset"] = function_offset

                response_stack.append(frame)

            # XXX Stop calling it this. It's an old word.
            result["symbolicatedStacks"].append(response_stack)

        t1 = time.time()

        logger.info(
            "The whole symbolication of {} ({} actual) "
            "stacks took {:.4f} seconds".format(total_stacks, real_stacks, t1 - t0)
        )

        if self.debug:
            result["debug"] = {
                "time": t1 - t0,
                "stacks": {"count": total_stacks, "real": real_stacks},
                "modules": {
                    "count": len(modules_lookups),
                    "stacks_per_module": stacks_per_module,
                },
                "cache_lookups": {
                    "count": len(cache_lookup_times),
                    "time": float(sum(cache_lookup_times)),
                },
                "downloads": {
                    "count": len(download_times),
                    "time": float(sum(download_times)),
                    "size": float(sum(download_sizes)),
                },
            }

        return result

    @staticmethod
    def _get_nearest(offset_list, offset):
        """return the item in the list to the left nearst point.
        For example, if the 'offset_list' is: [10, 20, 30]
        and 'offset' is 25, the return 20.
        This function assumes that the 'offset_list' is sorted.
        This function also assumes that 'offset' is *not* in
        'offset_list'.

        The origin of this function is that we look for offsets in
        a stack as these are kinda like lines of code. Imagine this
        C++ program::

            10) ...
            11) void some_function() {
            12)     ...
            13)     ...
            14)     ...
            15) }
            17) void other_function() {
            18)     ...
            19) }
            20) ...

        Here, the 'offset_list' is going to be [11, 17]. The offsets
        where the functions are.
        Suppose the 'offset' we're being asked to look up is 13, meaning
        the interesting thing happened on "line" 13. The nearest "function
        definition line" is 11. That's where the function was defined.
        To find 11, we bisect the list of all offsets and subtract 1.
        I.e. bisect([11, 17], 13) == p == 1
        And [11, 17][p - 1] == 11
        """
        return offset_list[bisect(offset_list, offset) - 1]

    @staticmethod
    def _make_cache_key(symbol_key):
        return make_symbol_key_cache_key(symbol_key)

    @metrics.timer_decorator("symbolicate_get_symbol_maps")
    def get_symbol_offsets(self, symbol_keys):
        """Return a dict that contains the following keys:
            * 'symbols'
            * 'cache_lookup_times' (only present if self.debug==True)

        The 'symbols' key contains a dict that looks like this::

            {
                "xul.pdb/HEX": {
                    "found": True,
                    "symbol_offsets": [1235, 4577, 6412, 7800]
                },
                "win32.dll/HEX": {
                    "found": False,
                    "symbol_offsets": None  # Means it wasn't found in Redis
                }
            }

        To optimize the Redis lookups everything that can be queried
        "in batch" is done so. So multiple lookup keys get turned into
        a list just so we can do things like MGET Redis queries.
        """
        cache_keys = {self._make_cache_key(x): x for x in symbol_keys}
        redis_store_connection = get_redis_connection("store")
        cache_lookup_times = []

        # This is the dict we're going to build up. Each key is a
        # symbol key's cache key. Each value is a list of offsets.
        many = {}

        # Build up a list of the names of ALL keys that contains the
        # the keys.
        cache_keys_keys = []
        for cache_key in cache_keys:
            cache_keys_keys.append(cache_key + ":keys")
        t0 = time.time()
        # store.get_many() returns an OrderedDict() object that
        # maps each *available* key to their list of ALL hash map keys.
        all_keys = store.get_many(cache_keys_keys)
        t1 = time.time()
        cache_lookup_times.append(t1 - t0)

        # Important! Why aren't using Redis HKEYS?
        # tl;dr It's too slow.
        #
        # You *could* do this:
        #   > HSET foo key1 valueX
        #   > HSET foo key2 valueY
        #   > HSET foo key3 valueZ
        # ...and to get that list of [key1, key2, key3] you can do:
        #   > HKEYS foo
        #   1) key1
        #   2) key2
        #   3) key3
        #
        # But that's very slow. HKEYS is O(N).
        #
        # Instead, we do one extra simple SET for a list of all keys.
        # So like this:
        #   > HSET foo key1 valueX
        #   > HSET foo key2 valueY
        #   > HSET foo key3 valueZ
        #   > SET foo:keys "[key1, key2, key3]"
        #
        # Now, instead of HKEYS we use simple GET:
        #   > GET foo
        #   1) "[key1, key2, key3]"
        #
        # That list gets serialized (and compressed) by django_redis
        # so we don't have to worry about turning it back into a pure
        # Python list.
        #
        # The caveat is that we now have 2 "top level keys" (foo the
        # hash map and foo:keys the plain key/value).
        #
        # What *can* happen is that since the Redis store is configured
        # as a LRU cache, one of these might get evicted.
        # If the plain key/value "foo:keys" gets evicted, we plainly
        # assume it has never existed and we "start over" download
        # it from the Internet. Just as if we've never ever encounted
        # it before.
        # Alternatively, the hash map "foo" might have been evicted.
        # It's impossible to know so we have to make a HLEN query to
        # check if the hash map is still there.

        # If there are no offsets at all, it means there are no
        # hash maps of this symbol key. But perhaps we've previously
        # attempted to download the symbols file from the Internet
        # and failed. In that case, we don't want to repeatedly try
        # to download it again (and fail repeatedly).
        # All "failed" attempts are stored as regular keys with an
        # empty dict.
        # The reason for using a list is so that we can do an MGET
        # later.
        maybes = []

        for cache_key in cache_keys:
            keys = all_keys.get(cache_key + ":keys")
            if keys:
                # Cool! The list of all hash map keys exists in Redis.
                # But, what if the LRU kicked out the hash map??
                # The quickest way to find out is to ask to the length
                # of the hash map.
                t0 = time.time()
                length = redis_store_connection.hlen(store.make_key(cache_key))
                t1 = time.time()
                cache_lookup_times.append(t1 - t0)
                if not length:
                    # The list of keys existed but not the hashmap :(
                    keys = []
            if keys:
                many[cache_key] = keys
            else:
                maybes.append(cache_key)
        if maybes:
            t0 = time.time()
            empties = store.get_many(maybes)
            t1 = time.time()
            cache_lookup_times.append(t1 - t0)
            many.update(empties)

        t1 = time.time()

        # All Redis queries that can be done have been done.
        # Time to "package it up".

        informations = {"symbols": {}}
        for cache_key in cache_keys:
            symbol_key = cache_keys[cache_key]
            information = {}

            symbol_offsets = many.get(cache_key)
            if symbol_offsets is None:  # not existant in cache
                # Need to download this from the Internet.
                metrics.incr("symbolicate_symbol_key", tags=["cache:miss"])
                # If the symbols weren't in the cache, this will be dealt
                # with later by this method's caller.
                # XXX I don't like this! That would can be done here instead.
            else:
                # We *used* store the whole symbol map as a dict.
                # Both if it actually existed and both if it was not found
                # in S3.
                # This makes things complicated for upgrading existing
                # systems. So let's make a fix for that.
                if isinstance(symbol_offsets, dict):  # pragma: no cover
                    symbol_offsets = []

                assert isinstance(symbol_offsets, list), type(symbol_offsets)
                if not symbol_offsets:  # e.g. an empty list
                    # It was cached but empty. That means it was logged that
                    # it was previously attempted but failed.
                    # The reason it's cached is to avoid it being looked up
                    # again and again when it's just going to continue to fail.
                    information["symbol_offsets"] = []
                    information["found"] = False
                else:
                    metrics.incr("symbolicate_symbol_key", tags=["cache:hit"])
                    # If it was in cache, that means it was originally found.
                    information["symbol_offsets"] = symbol_offsets
                    information["found"] = True
            informations["symbols"][symbol_key] = information

        if self.debug:
            informations["cache_lookup_times"] = cache_lookup_times
        return informations

    def load_symbols(self, requirements):
        """return a list that contains items of 3-tuples of
        (symbol_key, information, module_index)
        """
        redis_store_connection = get_redis_connection("store")
        # This could be done concurrently, but from experience we see that
        # the LRU cache does a very good job staying warm and containing
        # lots of objects so it's rare that we need to download more things
        # from S3 via the network. If we do it's very often just 1 more
        # so there's little point in making that parallel.
        for symbol_key, module_index in requirements:
            cache_key = self._make_cache_key(symbol_key)
            information = {}
            try:
                information.update(self.load_symbol(*symbol_key))
                if not information["download_size"]:
                    raise SymbolFileEmpty()
                assert isinstance(information["symbol_map"], dict)

                with metrics.timer("symbolicate_store_hashmap"):
                    t0 = time.time()
                    # This big dict we're about to send to Redis with HMSET
                    # might be too large to fit and if it is too large
                    # redis-py will throw a ConnectionError with something
                    # like 'Errno 104' because Redis simply shuts down the
                    # socket.
                    # To avoid that, set this monster dict in batches.
                    # Empirically we found the ConnectionError happens when
                    # the dict, converted to a string, is around 9MB.
                    # Also empirically, the *average* value is 90 bytes and the
                    # average key is 8 bytes. So if each key+value is about
                    # 100 bytes, to make a batch of the dict into copies that
                    # are no larger than 5MB you have to read about 50,000
                    # keys at a time.
                    count = 0
                    buffer = {}
                    hmset_key = store.make_key(cache_key)
                    all_keys = []
                    for key in information["symbol_map"]:
                        all_keys.append(key)
                        buffer[key] = information["symbol_map"][key]
                        count += 1
                        if count > 50000:
                            redis_store_connection.hmset(hmset_key, buffer)
                            count = 0
                            buffer = {}
                    if count:
                        redis_store_connection.hmset(hmset_key, buffer)

                    store.set(cache_key + ":keys", all_keys, timeout=None)
                    t1 = time.time()

                store_time = t1 - t0

                logger.info(
                    "Storing hash map for {} ({} keys). "
                    "Took {:.2f}s to download. "
                    "Took {:.2f}s to store in LRU."
                    "".format(
                        "/".join(symbol_key),
                        format(len(all_keys), ","),
                        information["download_time"],
                        store_time,
                    )
                )
                information["found"] = True

            except (SymbolNotFound, SymbolFileEmpty):
                # If it can't be downloaded, cache it as an empty result
                # so we don't need to do this every time we're asked to
                # look up this symbol.
                metrics.incr("symbolicate_download_fail", 1)

                store.set(cache_key, [], settings.DEBUG and 6 or 60)
                # If nothing could be downloaded, keep it anyway but
                # to avoid having to check if 'symbol_map' is None, just
                # turn it into a dict.
                information["symbol_map"] = {}  # override
                information["found"] = False
            yield (symbol_key, information, module_index)

    @metrics.timer_decorator("symbolicate_load_symbol")
    def load_symbol(self, filename, debug_id):
        t0 = time.time()
        stream = self.get_download_symbol_stream(filename, debug_id)

        # We are only interested in lines start with "FUNC" or "PUBLIC" or
        # "PUBLIC m.
        # The "m" special. It's an extra *optional* prefix which,
        # we currently omit.
        # Origin: https://bugs.chromium.org/p/google-breakpad/issues/detail?id=751
        # Note, as pointed out in
        # https://github.com/mozilla-services/tecken/issues/924#issuecomment-399130860
        # some day we might actually extract and use the presence of this 'm'
        # as a potential factor of the symbolication.
        # As of June 2018, we deliberately omit it.

        # Need to parse it by line and make a dict of of offset->function
        public_symbols = {}
        func_symbols = {}
        line_number = 0
        total_size = 0
        t0 = time.time()
        url = next(stream)
        for line in stream:
            total_size += len(line)
            line_number += 1

            # Using `str1 in str2` is empirically the fastest operator there
            # is.
            # See
            # https://github.com/mozilla-services/tecken/issues/983#issuecomment-412142517
            # But it's inaccurate so we use this fast operator as a first
            # step. Then later, do we check that it really is a valid prefix.
            if "FUNC " in line or "PUBLIC " in line:
                prefix, rest = line.split(None, 1)
                # Perhaps the line was "Bbla bla FUNC bla bla"
                # and not "FUNC bla bla".
                if prefix not in ("FUNC", "PUBLIC"):
                    continue
                if rest.startswith("m "):
                    rest = rest[2:]
            else:
                continue

            if prefix == "PUBLIC":
                fields = rest.strip().split(None, 2)
                if len(fields) != 3:
                    logger.warning(
                        "PUBLIC line {} in {} has too few fields".format(
                            line_number, url
                        )
                    )
                    continue
                address = int(fields[0], 16)
                symbol = fields[2]
                public_symbols[address] = symbol
            elif prefix == "FUNC":
                fields = rest.strip().split(None, 3)
                if len(fields) != 4:
                    logger.warning(
                        "FUNC line {} in {} has too few fields".format(line_number, url)
                    )
                    continue
                address = int(fields[0], 16)
                symbol = fields[3]
                func_symbols[address] = symbol

        # Prioritize PUBLIC symbols over FUNC symbols # XXX why?
        func_symbols.update(public_symbols)
        t1 = time.time()
        if not total_size:
            logger.warning(
                "Downloaded content empty ({!r}, {!r})".format(filename, debug_id)
            )
        information = {}
        information["symbol_map"] = func_symbols
        information["download_time"] = t1 - t0
        information["download_size"] = total_size
        return information

    def get_download_symbol_stream(self, lib_filename, debug_id):
        """
        Return a requests.response stream or raise SymbolNotFound
        if the symbol can't be found at all.
        """
        if lib_filename.endswith(".pdb"):
            symbol_filename = lib_filename[:-4] + ".sym"
        else:
            symbol_filename = lib_filename + ".sym"

        stream = self.downloader.get_symbol_stream(
            lib_filename, debug_id, symbol_filename
        )
        return stream


def json_post(view_function):
    """The minimum for posting a symbolication request is that you use
    POST and that you have a valid JSON payload in the body."""

    @wraps(view_function)
    def inner(request):
        if request.method == "OPTIONS":
            return http.HttpResponse("")
        if request.method != "POST":
            return JsonResponse({"error": "Must use HTTP POST"}, status=405)

        try:
            json_body = json.loads(request.body.decode("utf-8"))
            if not isinstance(json_body, dict):
                return JsonResponse({"error": "Not a dict"}, status=400)
        except ValueError:
            return JsonResponse({"error": "Invalid JSON passed in"}, status=400)

        return view_function(request, json_body)

    return inner


class InvalidStacks(Exception):
    """Happens when the input stacks does not confirm to the standard."""

    # XXX This would perhaps be best replaced with a JSON Schema solution.


def validate_stacks(stacks):
    if not isinstance(stacks, list):
        raise InvalidStacks("Must be a list")

    for stack in stacks:
        if not isinstance(stack, list):
            raise InvalidStacks("Must be a list of lists")
        for frame in stack:
            if not isinstance(frame, list):
                raise InvalidStacks("Must be a list of lists of lists")
            if len(frame) != 2:
                raise InvalidStacks("List of lists of frames must be 2 numbers")
            if not (isinstance(frame[0], int) and isinstance(frame[1], int)):
                raise InvalidStacks("Frame must be two integers")


class InvalidMemoryMap(Exception):
    """Happens when the input memoryMap does not confirm to the standard."""


def validate_memory_map(memory_map):
    if not isinstance(memory_map, list):
        raise InvalidMemoryMap("Must be a list")

    for each in memory_map:
        if not isinstance(each, list) or len(each) != 2:
            raise InvalidMemoryMap("Must be a list of lists of size 2")
        module_name, debug_id = each
        if len(module_name) > 1024:
            raise InvalidMemoryMap("module name too long")
        if not debug_id:
            raise InvalidMemoryMap("debugID empty or missing")
        if "\x00" in module_name:
            raise InvalidMemoryMap("module_name contains null-byte")


@set_cors_headers(origin="*", methods="POST")
@csrf_exempt
@set_request_debug
@metrics.timer_decorator("symbolicate_json", tags=["version:v4"])
@json_post
def symbolicate_v4_json(request, json_body):

    try:
        stacks = json_body["stacks"]
        try:
            validate_stacks(stacks)
        except InvalidStacks as exception:
            return JsonResponse({"error": str(exception)}, status=400)
        memory_map = json_body["memoryMap"]
        if json_body.get("version") != 4:
            return JsonResponse({"error": "Expect version==4"}, status=400)
    except KeyError as exception:
        return JsonResponse(
            {"error": 'Missing key JSON "{}"'.format(exception)}, status=400
        )

    symbolicator = SymbolicateJSON(downloader, debug=request._request_debug)
    try:
        result = symbolicator.symbolicate(stacks, memory_map)
    except operational_exceptions as exception:
        return http.HttpResponse(str(exception), status=503)
    # except SymbolDownloader as exception:
    #     return http.HttpResponse(str(exception), status=503)
    # The result will have 'symbolicatedStacks' list that isn't in the
    # old v4 format so we have to rewrite it.

    def rewrite_dict_to_list(d):
        if "function" not in d:
            try:
                function = hex(d["module_offset"])
            except TypeError:
                # Happens if 'module_offset' is not an int16
                # and thus can't be represented in hex.
                function = str(d["module_offset"])
        else:
            function = d["function"]
        return "{} (in {})".format(function, d["module"])

    increment_symbolication_count("v4")
    metrics.incr("symbolicate_symbolication", tags=["version:v4"])

    for i, stack in enumerate(result["symbolicatedStacks"]):
        result["symbolicatedStacks"][i] = [rewrite_dict_to_list(x) for x in stack]
    return JsonResponse(result)


@set_cors_headers(origin="*", methods=["OPTIONS", "POST"])
@csrf_exempt
@set_request_debug
@metrics.timer_decorator("symbolicate_json", tags=["version:v5"])
@json_post
def symbolicate_v5_json(request, json_body):
    """The sent in JSON body is expected to be a dict that looks like this:

        {
            "jobs": [
                STACK1,
                STACK2,
                STACK-N,
            ]
        }

    Where 'STACK-N' is a struct like this:

        {
            "memoryMap": [
                ["xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2"],
                ["wntdll.pdb", "D74F79EB1F8D4A45ABCD2F476CCABACC2"]
            ],
            "stacks": [
                [
                    [0, 11723767], [1, 65802]
                ],
                [
                    [0, 1002], [0, 21456], [1, 65803]
                ],
            ]
        }

    However, for convenience, if the JSON is only 'STACK-N' and not a
    dictionary with key "stacks", we'll just wrap it for you.
    """
    if "stacks" in json_body and "memoryMap" in json_body:
        # Allow this to be passed in for convenience but "force"
        # it into the dict with a list of all stacks.
        json_body = {"jobs": [json_body]}
        # But note! Even if you do this, you'll always get a dict with
        # a *list* of stacks.

    # Before we actually unpack it, loop over it to make sure all things
    # are there.
    try:
        if not json_body["jobs"]:
            # Key is there but either None, False or []
            return JsonResponse({"error": "Jobs list empty"}, status=400)
        for i, stack in enumerate(json_body["jobs"]):
            if not isinstance(stack["memoryMap"], list):
                raise TypeError(f"Stack number {i + 1} is 'memoryMap' not a list")
            # Should be a list of two items.
            if not isinstance(stack["stacks"], list):
                raise TypeError(f"Stack number {i + 1} is 'stacks' not a list")
    except KeyError as exception:
        return JsonResponse({"error": f"Missing key in JSON ({exception})"}, status=400)
    except TypeError as exception:
        return JsonResponse({"error": f"Wrong type of value ({exception})"}, status=400)

    # By creating 1 instance per multiple jobs, we can benefit from
    # re-used downloads of memory maps.
    symbolicator = SymbolicateJSON(downloader, debug=request._request_debug)
    results = {"results": []}

    def serialize_frames(frames):
        for frame in frames:
            try:
                frame["module_offset"] = hex(frame["module_offset"])
            except TypeError:
                # Happens if 'module_offset' is not an int16
                # and thus can't be represented in hex.
                frame["module_offset"] = str(frame["module_offset"])
            if "function_offset" in frame and frame.get("function"):
                frame["function_offset"] = hex(frame["function_offset"])
        return frames

    increment_symbolication_count("v5")
    metrics.incr("symbolicate_symbolication", tags=["version:v5"])
    metrics.incr(
        "symbolicate_symbolication_jobs", len(json_body["jobs"]), tags=["version:v5"]
    )

    try:
        for job in json_body["jobs"]:
            try:
                validate_stacks(job["stacks"])
            except InvalidStacks as exception:
                return JsonResponse({"error": str(exception)}, status=400)
            try:
                validate_memory_map(job["memoryMap"])
            except InvalidMemoryMap as exception:
                return JsonResponse({"error": str(exception)}, status=400)

            result = symbolicator.symbolicate(job["stacks"], job["memoryMap"])
            found_modules = {}
            for i, module in enumerate(job["memoryMap"]):
                found_modules["/".join(module)] = result["knownModules"][i]

            job_result = {
                "stacks": [serialize_frames(x) for x in result["symbolicatedStacks"]],
                "found_modules": found_modules,
            }
            if "debug" in result:
                job_result["debug"] = result["debug"]
            results["results"].append(job_result)
        return JsonResponse(results)
    except operational_exceptions as exception:
        return http.HttpResponse(str(exception), status=503)
