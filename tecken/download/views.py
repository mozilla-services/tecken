# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

import markus

from django import http
from django.conf import settings
from django.urls import reverse

from tecken.base.decorators import (
    set_request_debug,
    api_require_http_methods,
    set_cors_headers,
)
from tecken.base.symboldownloader import SymbolDownloader
from tecken.base.utils import invalid_key_name_characters
from tecken.storage import StorageBucket
from tecken.upload.models import FileUpload


logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")


BOGUS_DEBUG_ID = "000000000000000000000000000000000"


normal_downloader = SymbolDownloader(
    settings.SYMBOL_URLS, file_prefix=settings.SYMBOL_FILE_PREFIX
)
try_downloader = SymbolDownloader(
    settings.SYMBOL_URLS + [settings.UPLOAD_TRY_SYMBOLS_URL],
    file_prefix=settings.SYMBOL_FILE_PREFIX,
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


def download_symbol_try(request, debugfilename, debugid, filename):
    return download_symbol(request, debugfilename, debugid, filename, try_symbols=True)


def lookup_by_code_file_code_id(code_file, code_id):
    """Returns the debug_filename/debug_id for given code_file/code_id

    This is only useful for Windows module sym files. Other platforms don't have valid
    code_file/code_id values.

    :arg code_file: the code_file to look up with; ex. "xul.dll"
    :arg code_id: the code_id to look up with

    :returns: dict with (debug_filename, debug_id) keys or None if there's no such
        record

    """
    logger.debug(f"lookup by code_file={code_file!r} code_id={code_id!r}")
    file_upload = (
        FileUpload.objects.filter(code_file=code_file, code_id=code_id)
        .order_by("created_at")
        .last()
    )

    if file_upload:
        return {
            "debug_filename": file_upload.debug_filename,
            "debug_id": file_upload.debug_id,
        }


@metrics.timer_decorator("download_symbol")
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

    # If we can't find the file, maybe it's in the form
    # /{code_file}/{code_id}/{sym_file}, so see if we have a record with that
    # code_file/code_id combination
    ret = lookup_by_code_file_code_id(code_file=debugfilename, code_id=debugid)
    if ret:
        new_url = reverse(
            "download:download_symbol",
            args=(ret["debug_filename"], ret["debug_id"], filename),
        )
        if request.GET:
            new_url = f"{new_url}?{request.GET.urlencode()}"
        metrics.incr("download_symbol_code_id_lookup")
        return http.HttpResponseRedirect(new_url)

    response = http.HttpResponseNotFound("Symbol Not Found")
    if request._request_debug:
        response["Debug-Time"] = downloader.time_took
    return response
