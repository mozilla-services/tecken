# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging


from django import http
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from tecken.base.decorators import (
    set_request_debug,
    api_require_http_methods,
    set_cors_headers,
)
from tecken.base.symboldownloader import SymbolDownloader
from tecken.base.utils import invalid_key_name_characters
from tecken.upload.models import FileUpload
from tecken.storage import StorageBucket
from tecken.libmarkus import METRICS


logger = logging.getLogger("tecken")


BOGUS_DEBUG_ID = "000000000000000000000000000000000"


normal_downloader = SymbolDownloader(
    settings.SYMBOL_URLS, file_prefix=settings.SYMBOL_FILE_PREFIX
)
try_downloader = SymbolDownloader(
    settings.SYMBOL_URLS + [settings.UPLOAD_TRY_SYMBOLS_URL],
    file_prefix=settings.SYMBOL_FILE_PREFIX,
    try_url_index=len(settings.SYMBOL_URLS),
)


def _ignore_symbol(debugfilename, debugid, filename):
    # The MS debugger will always try to look up these files. We
    # never have them in our symbol stores. So it can be safely ignored.
    if filename == "file.ptr":
        return True

    if debugid == BOGUS_DEBUG_ID:
        return True

    if not filename.endswith(tuple(settings.DOWNLOAD_FILE_EXTENSIONS_ALLOWED)):
        return True

    # The default is to NOT ignore it
    return False


# Store a result for 10 minutes
SYMINFO_RESULT_CACHE_TIMEOUT = 600

# Indicates there's nothing in the cache
NO_VALUE_IN_CACHE = object()


@METRICS.timer_decorator("syminfo.lookup.timing")
def cached_lookup_by_syminfo(somefile, someid, refresh_cache=False):
    """Looks up somefile/someid in fileupload data; caches result

    This value is cached.

    :arg somefile: a string that's either a debug_file or a code_file
    :arg someid: a string that's either a debug_id or a code_id
    :arg refresh_cache: force a cache refresh

    :returns: dict with (key, debug_filename, debug_id, code_file, code_id, generator)
        keys

    NOTE(willkg): This doesn't differentiate between try symbols and regular symbols.
    It's probably the case that something is requesting using codeinfo wants to query
    try symbols as well.

    """
    key = f"lookup_by_syminfo::{somefile}//{someid}"
    data = cache.get(key, default=NO_VALUE_IN_CACHE)
    if data is NO_VALUE_IN_CACHE or refresh_cache is True:
        qs = FileUpload.objects.lookup_by_syminfo(some_file=somefile, some_id=someid)
        data = qs.values(
            "key", "debug_filename", "debug_id", "code_file", "code_id", "generator"
        ).last()

        cache.set(key, data, SYMINFO_RESULT_CACHE_TIMEOUT)
        METRICS.incr("syminfo.lookup.cached", tags=["result:false"])
    else:
        METRICS.incr("syminfo.lookup.cached", tags=["result:true"])

    return data


def is_maybe_codeinfo(some_file, some_id, filename):
    """Returns true if this is possibly a codeinfo.

    :arg some_file: a filename; a code file will end with ".dll" or ".exe" or something
        like that
    :arg some_id: an id; a code id that's hex characters and less than 33
        characters long
    :arg filename: a symbol file that ends wtih ".sym"

    :returns: bool

    """
    return (
        bool(filename)
        and filename.endswith(".sym")
        and bool(some_file)
        and bool(some_id)
        # NOTE(willkg): debug ids are 33 characters and code ids can vary; further
        # some_id is guaranteed to be hex characters because of the urlpattern
        and len(some_id) < 33
    )


def download_symbol_try(request, debugfilename, debugid, filename):
    return download_symbol(request, debugfilename, debugid, filename, try_symbols=True)


@METRICS.timer_decorator("download_symbol")
@set_request_debug
@api_require_http_methods(["GET", "HEAD"])
@set_cors_headers(origin="*", methods="GET")
def download_symbol(request, debugfilename, debugid, filename, try_symbols=False):
    # First there's an opportunity to do some basic pattern matching on the symbol,
    # debugid, and filename parameters to determine if we can, with confidence, simply
    # ignore it.
    #
    # Not only can we avoid doing a SymbolDownloader call, we also don't have to bother
    # logging that it could not be found.
    if _ignore_symbol(debugfilename, debugid, filename):
        logger.debug(f"Ignoring symbol {debugfilename}/{debugid}/{filename}")
        response = http.HttpResponseNotFound("Symbol Not Found (and ignored)")
        if request._request_debug:
            response["Debug-Time"] = 0
        return response

    if invalid_key_name_characters(debugfilename + filename):
        logger.debug(f"Invalid character {debugfilename!r}/{debugid}/{filename!r}")
        response = http.HttpResponseBadRequest(
            "Symbol name lookup contains invalid characters and will never be found."
        )
        if request._request_debug:
            response["Debug-Time"] = 0
        return response

    refresh_cache = "_refresh" in request.GET

    if "try" in request.GET or try_symbols:
        downloader = try_downloader
    else:
        downloader = normal_downloader

    if request.method == "HEAD":
        if downloader.has_symbol(
            debugfilename, debugid, filename, refresh_cache=refresh_cache
        ):
            response = http.HttpResponse()
            if request._request_debug:
                response["Debug-Time"] = downloader.time_took
            return response

    else:
        url = downloader.get_symbol_url(
            debugfilename, debugid, filename, refresh_cache=refresh_cache
        )
        if url:
            # If doing local development, with Docker, you're most likely running
            # localstack as a fake S3. It runs on its own hostname that is only
            # available from other Docker containers. But to make it really convenient,
            # for testing symbol download we'll rewrite the URL to one that is possible
            # to reach from the host.
            if (
                settings.DEBUG
                and StorageBucket(url).backend == "emulated-s3"
                and "http://localstack:4566" in url
                and request.get_host() == "localhost:8000"
            ):  # pragma: no cover
                url = url.replace("localstack:4566", "localhost:4566")
            response = http.HttpResponseRedirect(url)
            if request._request_debug:
                response["Debug-Time"] = downloader.time_took
            return response

    if is_maybe_codeinfo(debugfilename, debugid, filename):
        ret = cached_lookup_by_syminfo(
            somefile=debugfilename, someid=debugid, refresh_cache=refresh_cache
        )
        if ret:
            # Redirect to the correct debuginfo download url
            if "try" in request.GET or try_symbols:
                view_to_use = "download:download_symbol_try"
            else:
                view_to_use = "download:download_symbol"

            new_url = reverse(
                view_to_use,
                args=(ret["debug_filename"], ret["debug_id"], filename),
            )
            if request.GET:
                new_url = f"{new_url}?{request.GET.urlencode()}"
            METRICS.incr("download_symbol_code_id_lookup")
            return http.HttpResponseRedirect(new_url)

    response = http.HttpResponseNotFound("Symbol Not Found")
    if request._request_debug:
        response["Debug-Time"] = downloader.time_took
    return response
