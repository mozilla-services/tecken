# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import csv
import datetime
import hashlib
import logging

import markus
from cache_memoize import cache_memoize

from django import http
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from django.utils.encoding import force_bytes
from django.db import OperationalError

from tecken.base.utils import invalid_s3_key_name_characters
from tecken.base.symboldownloader import SymbolDownloader
from tecken.base.decorators import (
    set_request_debug,
    api_require_http_methods,
    set_cors_headers,
)
from tecken.download.models import MissingSymbol
from tecken.download.utils import store_missing_symbol
from tecken.download.tasks import (
    download_microsoft_symbol,
    store_missing_symbol_task
)

logger = logging.getLogger('tecken')
metrics = markus.get_metrics('tecken')


normal_downloader = SymbolDownloader(
    settings.SYMBOL_URLS,
    file_prefix=settings.SYMBOL_FILE_PREFIX,
)
try_downloader = SymbolDownloader(
    settings.SYMBOL_URLS + [settings.UPLOAD_TRY_SYMBOLS_URL],
    file_prefix=settings.SYMBOL_FILE_PREFIX,
)

# Set it "globally" here the module on import-time so we don't have to
# repeatly get it from the settings module in runtime.
file_extensions_whitelist = tuple(settings.DOWNLOAD_FILE_EXTENSIONS_WHITELIST)


def _ignore_symbol(symbol, debugid, filename):
    # The MS debugger will always try to look up these files. We
    # never have them in our symbol stores. So it can be safely ignored.
    if filename == 'file.ptr':
        return True
    if debugid == '000000000000000000000000000000000':
        return True

    if not filename.endswith(file_extensions_whitelist):
        return True

    # The default is to NOT ignore it
    return False


# Note! The reason this can't use the cache_memoize decorator
# is because we need tight control of what the cache key becomes. That
# way we can cache invalidate it later.
def download_from_microsoft(
    symbol,
    debugid,
    code_file=None,
    code_id=None,
    missing_symbol_hash=None
):
    """Only kick off the 'download_microsoft_symbol' background task
    if we haven't already done so recently."""

    cache_key = hashlib.md5(force_bytes(
        f'microsoft-download:{symbol}:{debugid}'
    )).hexdigest()
    if not cache.get(cache_key):
        # Commence the background task to try to download from Microsoft
        download_microsoft_symbol.delay(
            symbol,
            debugid,
            code_file=code_file,
            code_id=code_id,
            missing_symbol_hash=missing_symbol_hash or None
        )
        cache.set(
            cache_key,
            True,
            settings.MICROSOFT_DOWNLOAD_CACHE_TTL_SECONDS
        )


@metrics.timer_decorator('download_symbol')
@set_request_debug
@api_require_http_methods(['GET', 'HEAD'])
@set_cors_headers(origin='*', methods='GET')
def download_symbol(request, symbol, debugid, filename):
    # First there's an opportunity to do some basic pattern matching on
    # the symbol, debugid, and filename parameters to determine
    # if we can, with confidence, simply ignore it.
    # Not only can we avoid doing a SymbolDownloader call, we also
    # don't have to bother logging that it could not be found.
    if _ignore_symbol(symbol, debugid, filename):
        logger.debug(f'Ignoring symbol {symbol}/{debugid}/{filename}')
        response = http.HttpResponseNotFound('Symbol Not Found (and ignored)')
        if request._request_debug:
            response['Debug-Time'] = 0
        return response

    if invalid_s3_key_name_characters(symbol + filename):
        logger.debug(f'Invalid character {symbol!r}/{debugid}/{filename!r}')
        response = http.HttpResponseBadRequest(
            'Symbol name lookup contains invalid characters and will never '
            'be found.'
        )
        if request._request_debug:
            response['Debug-Time'] = 0
        return response

    refresh_cache = '_refresh' in request.GET

    if 'try' in request.GET:
        downloader = try_downloader
    else:
        downloader = normal_downloader

    if request.method == 'HEAD':
        if downloader.has_symbol(
            symbol,
            debugid,
            filename,
            refresh_cache=refresh_cache,
        ):
            response = http.HttpResponse()
            if request._request_debug:
                response['Debug-Time'] = downloader.time_took
            return response
    else:
        url = downloader.get_symbol_url(
            symbol,
            debugid,
            filename,
            refresh_cache=refresh_cache,
        )
        if url:
            # If doing local development, with Docker, you're most likely
            # running minio as a fake S3 client. It runs on its own
            # hostname that is only available from other Docker containers.
            # But to make it really convenient, for testing symbol download
            # we'll rewrite the URL to one that is possible to reach
            # from the host.
            if (
                settings.DEBUG and
                'http://minio:9000' in url and
                request.get_host() == 'localhost:8000'
            ):  # pragma: no cover
                url = url.replace('minio:9000', 'localhost:9000')
            response = http.HttpResponseRedirect(url)
            if request._request_debug:
                response['Debug-Time'] = downloader.time_took
            return response

    # Assume that we don't do a delayed (background task) lookup and
    # have not done one recently either.
    delayed_lookup = False

    if request.method == 'GET':
        # Only bother logging it if the client used GET.
        # Otherwise it won't be possible to pick up the extra
        # query string parameters.
        missing_symbol_hash = log_symbol_get_404(
            symbol,
            debugid,
            filename,
            code_file=request.GET.get('code_file'),
            code_id=request.GET.get('code_id'),
        )

        if (
            settings.ENABLE_DOWNLOAD_FROM_MICROSOFT and
            symbol.lower().endswith('.pdb') and
            filename.lower().endswith('.sym')

        ):
            # The log_symbol_get_404() function is protected by a cache
            # that "guards" it with a memoize decorator. That memoize
            # decorator makes sure the same arguments aren't allowed
            # in more than once (per time interval the memoize cache
            # is configured to).
            # However, if it did run (and wasn't memoize blocked), it
            # yields a hash to "describe" the missing symbol. That's
            # useful to have when downloading from Microsoft.
            # The function 'download_from_microsoft()' is will
            # get or create one of those hashes no matter what. Here
            # we're just doing a little optimization by passing that
            # along to download_from_microsoft() to save it some effort.
            if missing_symbol_hash and isinstance(missing_symbol_hash, bool):
                missing_symbol_hash = None

            # If we haven't already sent it to the 'download_microsoft_symbol'
            # background task, do so.
            download_from_microsoft(
                symbol,
                debugid,
                code_file=request.GET.get('code_file'),
                code_id=request.GET.get('code_id'),
                missing_symbol_hash=missing_symbol_hash,
            )

            # The querying of Microsoft's server is potentially slow.
            # That's why this call is down in a celery task.
            # But there is hope! And the client ought to be informed
            # that if they just try again in a couple of seconds/minutes
            # it might just be there.
            delayed_lookup = True

    response = http.HttpResponseNotFound(
        'Symbol Not Found Yet' if delayed_lookup else 'Symbol Not Found'
    )
    if request._request_debug:
        response['Debug-Time'] = downloader.time_took
    return response


@cache_memoize(
    settings.MEMOIZE_LOG_MISSING_SYMBOLS_SECONDS,
    # When you just want this to be a "guard" that protects it from
    # executing more than once.
    store_result=False,
)
@metrics.timer('download_log_symbol_get_404')
def log_symbol_get_404(
    symbol,
    debugid,
    filename,
    code_file='',
    code_id='',
):
    """Store the fact that a symbol could not be found.

    The purpose of this is be able to answer "What symbol fetches have
    recently been attempted and failed?" With that knowledge, we can
    deduce which symbols are commonly needed in symbolication but failed
    to be available. Then you can try to go and get hold of them and
    thus have less symbol 404s in the future.

    Because this is expected to be called A LOT (in particular from
    Socorro's Processor) we have to do this rapidly in a database
    that is suitable for many fast writes.
    See https://bugzilla.mozilla.org/show_bug.cgi?id=1361854#c5
    for the backstory about expected traffic.

    The URL used when requesting the file will only ever be
    'symbol', 'debugid' and 'filename', but some services, like Socorro's
    stackwalker is actually aware of other parameters that are
    relevant only to this URL. Hence 'code_file' and 'code_id' which
    are both optional.
    """
    if settings.ENABLE_STORE_MISSING_SYMBOLS:
        try:
            return store_missing_symbol(
                symbol,
                debugid,
                filename,
                code_file=code_file,
                code_id=code_id,
            )
        except OperationalError as exception:
            # Note that this doesn't return. The reason is because it's
            # a background job. We can only fire-and-forget sending it.
            # That's why we only do this in the unusual case of an
            # operational error.
            # By sending it to a background task, it gets to try storing
            # it again. The reasons that's more like to work is because...
            #
            #   A) There's a natural delay until it tries the DB
            #      write. Perhaps that little delay is all we need to try
            #      again and be lucky.
            #   B) The celery tasks have built-in support for retrying.
            #      So if it fails the first time (which is already unlikely)
            #      you get a second chance after some deliberate sleep.
            #
            # The return value is only rarely useful. It's used to indicate
            # that it *just* now got written down. And that's useful to know
            # when we attempt to automatically download it from Microsoft.
            store_missing_symbol_task.delay(
                symbol,
                debugid,
                filename,
                code_file=code_file,
                code_id=code_id,
            )


def missing_symbols_csv(request):
    """return a CSV payload that has yesterdays missing symbols.

    We have a record of every 'symbol', 'debugid', 'filename', 'code_file'
    and 'code_id'. In the CSV export we only want 'symbol', 'debugid',
    'code_file' and 'code_id'.

    There's an opportunity of optimization here.
    This payload is pretty large and requires a lot of memory to generate
    and respond. We could instead use an S3 bucket to store this and
    let S3 handle the download repeatedly.

    Note that this view is expected to be quite resource intensive.
    In Socorro we used to upload a .csv file to S3 on a daily basis.
    This file is what's downloaded and parsed to figure what needs to be
    improved in the symbol store ultimately. We could do some serious
    caching of this view by letting it generate *to* S3 if it hasn't
    already been generated and uploaded to S3.
    """

    date = timezone.now()
    if not request.GET.get('today'):
        # By default we want to look at keys inserted yesterday, but
        # it's useful (for debugging for example) to be able to see what
        # keys have been inserted today.
        date -= datetime.timedelta(days=1)

    response = http.HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        'attachment; filename="missing-symbols-{}.csv"'.format(
            date.strftime('%Y-%m-%d')
        )
    )
    writer = csv.writer(response)
    writer.writerow([
        'debug_file',
        'debug_id',
        'code_file',
        'code_id',
    ])

    # By default, only do those updated in the last 24h
    qs = MissingSymbol.objects.filter(
        modified_at__gte=date,
    )

    if request.GET.get('microsoft') == 'only':
        # This is a trick to immediately limit the symbols that could
        # be gotten from a Microsoft download.
        qs = qs.filter(
            symbol__iendswith='.pdb',
            filename__iendswith='.sym'
        )

    only = ('symbol', 'debugid', 'code_file', 'code_id')
    for missing in qs.only(*only).order_by('-modified_at'):
        writer.writerow([
            missing.symbol,
            missing.debugid,
            missing.code_file,
            missing.code_id,
        ])

    return response
