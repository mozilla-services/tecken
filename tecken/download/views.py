# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import markus

from django import http
from django.conf import settings

from tecken.base.decorators import (
    set_request_debug,
    api_require_http_methods,
    set_cors_headers,
)
from tecken.base.symboldownloader import SymbolDownloader
from tecken.base.utils import invalid_key_name_characters
from tecken.download.forms import DownloadForm
from tecken.storage import StorageBucket

logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")


normal_downloader = SymbolDownloader(
    settings.SYMBOL_URLS, file_prefix=settings.SYMBOL_FILE_PREFIX
)
try_downloader = SymbolDownloader(
    settings.SYMBOL_URLS + [settings.UPLOAD_TRY_SYMBOLS_URL],
    file_prefix=settings.SYMBOL_FILE_PREFIX,
)


def _ignore_symbol(symbol, debugid, filename):
    # The MS debugger will always try to look up these files. We
    # never have them in our symbol stores. So it can be safely ignored.
    if filename == "file.ptr":
        return True

    if debugid == "000000000000000000000000000000000":
        return True

    if not filename.endswith(tuple(settings.DOWNLOAD_FILE_EXTENSIONS_ALLOWED)):
        return True

    # The default is to NOT ignore it
    return False


def download_symbol_try(request, symbol, debugid, filename):
    return download_symbol(request, symbol, debugid, filename, try_symbols=True)


@metrics.timer_decorator("download_symbol")
@set_request_debug
@api_require_http_methods(["GET", "HEAD"])
@set_cors_headers(origin="*", methods="GET")
def download_symbol(request, symbol, debugid, filename, try_symbols=False):
    # First there's an opportunity to do some basic pattern matching on the symbol,
    # debugid, and filename parameters to determine if we can, with confidence, simply
    # ignore it.
    #
    # Not only can we avoid doing a SymbolDownloader call, we also don't have to bother
    # logging that it could not be found.
    if _ignore_symbol(symbol, debugid, filename):
        logger.debug(f"Ignoring symbol {symbol}/{debugid}/{filename}")
        response = http.HttpResponseNotFound("Symbol Not Found (and ignored)")
        if request._request_debug:
            response["Debug-Time"] = 0
        return response

    if invalid_key_name_characters(symbol + filename):
        logger.debug(f"Invalid character {symbol!r}/{debugid}/{filename!r}")
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
            symbol, debugid, filename, refresh_cache=refresh_cache
        ):
            response = http.HttpResponse()
            if request._request_debug:
                response["Debug-Time"] = downloader.time_took
            return response

    else:
        url = downloader.get_symbol_url(
            symbol, debugid, filename, refresh_cache=refresh_cache
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

    if request.method == "GET":
        # If the request was a GET, we can return a more helpful response especially
        # if the arguments were bad.
        form = DownloadForm(request.GET)
        if not form.is_valid():
            # Even if there might be more than one error, just exit out on the first
            # one. It's not important to know all the errors if there is at least one.
            for key in form.errors:
                for message in form.errors[key]:
                    return http.HttpResponseBadRequest(f"{key}: {message}")

    response = http.HttpResponseNotFound("Symbol Not Found")
    if request._request_debug:
        response["Debug-Time"] = downloader.time_took
    return response
