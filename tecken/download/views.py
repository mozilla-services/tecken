import csv
import datetime
import logging

import markus
from cache_memoize import cache_memoize

from django import http
from django.conf import settings
from django.utils import timezone
from django.db import OperationalError

from tecken.base.decorators import (
    set_request_debug,
    api_require_http_methods,
    set_cors_headers,
)
from tecken.base.form_utils import filter_form_dates, PaginationForm
from tecken.base.symboldownloader import SymbolDownloader
from tecken.base.utils import invalid_key_name_characters
from tecken.download.models import MissingSymbol
from tecken.download.utils import store_missing_symbol
from tecken.download.tasks import store_missing_symbol_task
from tecken.download.forms import DownloadForm, DownloadsMissingForm
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


def download_symbol_legacy(request, legacyproduct, symbol, debugid, filename):
    if legacyproduct not in settings.DOWNLOAD_LEGACY_PRODUCTS_PREFIXES:
        raise http.Http404("Invalid legacy product prefix")
    metrics.incr("download_legacyproduct")
    return download_symbol(request, symbol, debugid, filename)


def download_symbol_try(request, symbol, debugid, filename):
    return download_symbol(request, symbol, debugid, filename, try_symbols=True)


@metrics.timer_decorator("download_symbol")
@set_request_debug
@api_require_http_methods(["GET", "HEAD"])
@set_cors_headers(origin="*", methods="GET")
def download_symbol(request, symbol, debugid, filename, try_symbols=False):
    # First there's an opportunity to do some basic pattern matching on
    # the symbol, debugid, and filename parameters to determine
    # if we can, with confidence, simply ignore it.
    # Not only can we avoid doing a SymbolDownloader call, we also
    # don't have to bother logging that it could not be found.
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
            # If doing local development, with Docker, you're most likely
            # running minio as a fake S3 client. It runs on its own
            # hostname that is only available from other Docker containers.
            # But to make it really convenient, for testing symbol download
            # we'll rewrite the URL to one that is possible to reach
            # from the host.
            if (
                settings.DEBUG
                and StorageBucket(url).backend == "emulated-s3"
                and "http://minio:9000" in url
                and request.get_host() == "localhost:8000"
            ):  # pragma: no cover
                url = url.replace("minio:9000", "localhost:9000")
            response = http.HttpResponseRedirect(url)
            if request._request_debug:
                response["Debug-Time"] = downloader.time_took
            return response

    if request.method == "GET":
        # Only bother looking at the query string if the request was GET.
        form = DownloadForm(request.GET)
        if not form.is_valid():
            # Even if there might be more than one error, just exit
            # out on the first one. It's not important to know
            # all the errors if there is at least one.
            for key in form.errors:
                for message in form.errors[key]:
                    return http.HttpResponseBadRequest(f"{key}: {message}")
        else:
            code_file = form.cleaned_data["code_file"]
            code_id = form.cleaned_data["code_id"]

        # Only bother logging it if the client used GET.  Otherwise it won't be
        # possible to pick up the extra query string parameters.
        log_symbol_get_404(
            symbol, debugid, filename, code_file=code_file, code_id=code_id
        )

    response = http.HttpResponseNotFound("Symbol Not Found")
    if request._request_debug:
        response["Debug-Time"] = downloader.time_took
    return response


@cache_memoize(
    settings.MEMOIZE_LOG_MISSING_SYMBOLS_SECONDS,
    # When you just want this to be a "guard" that protects it from
    # executing more than once.
    store_result=False,
)
@metrics.timer("download_log_symbol_get_404")
def log_symbol_get_404(symbol, debugid, filename, code_file="", code_id=""):
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
                symbol, debugid, filename, code_file=code_file, code_id=code_id
            )
        except OperationalError:
            store_missing_symbol_task.delay(
                symbol, debugid, filename, code_file=code_file, code_id=code_id
            )


@metrics.timer("missingsymbols_csv")
def missingsymbols_csv(request):
    """Return a CSV payload that has yesterdays missing symbols

    We have a record of every 'symbol', 'debugid', 'filename', 'code_file' and
    'code_id'. In the CSV export we only want 'symbol', 'debugid', 'code_file'
    and 'code_id'.

    FIXME(willkg): This doesn't change day-to-day (unless you specify today, so
    maybe we should generate this and save/cache it?

    """
    date = timezone.now()
    if not request.GET.get("today"):
        # By default we want to look at keys inserted yesterday, but
        # it's useful (for debugging for example) to be able to see what
        # keys have been inserted today.
        date -= datetime.timedelta(days=1)

    response = http.HttpResponse(content_type="text/csv")
    response[
        "Content-Disposition"
    ] = 'attachment; filename="missing-symbols-{}.csv"'.format(
        date.strftime("%Y-%m-%d")
    )
    writer = csv.writer(response)
    writer.writerow(["debug_file", "debug_id", "code_file", "code_id"])

    # By default, only do those updated in the last 24h
    qs = MissingSymbol.objects.filter(
        modified_at__gte=date,
        # This is a trick to immediately limit the symbols that could be gotten
        # from a Microsoft download.
        symbol__iendswith=".pdb",
        filename__iendswith=".sym",
    )

    fields = ("symbol", "debugid", "code_file", "code_id")
    for missing in qs.values_list(*fields):
        writer.writerow(missing)

    return response


@metrics.timer("missingsymbols")
def missingsymbols(request):
    context = {}
    form = DownloadsMissingForm(request.GET)
    if not form.is_valid():
        return http.JsonResponse({"errors": form.errors}, status=400)

    qs = MissingSymbol.objects.all()
    # Apply date filters
    qs = filter_form_dates(qs, form, ("created_at", "modified_at"))

    # Apply symbol, debugid, filename filters
    for key in ("symbol", "debugid", "filename"):
        if form.cleaned_data[key]:
            qs = qs.filter(**{f"{key}__contains": form.cleaned_data[key]})

    # Apply order_by
    if form.cleaned_data.get("order_by"):
        order_by = form.cleaned_data["order_by"]
    else:
        order_by = {"sort": "modified_at", "reverse": True}
    order_by_string = ("-" if order_by["reverse"] else "") + order_by["sort"]
    qs = qs.order_by(order_by_string)
    context["order_by"] = order_by

    # Figure out page
    pagination_form = PaginationForm(request.GET)
    if not pagination_form.is_valid():
        return http.JsonResponse({"errors": pagination_form.errors}, status=400)

    page = pagination_form.cleaned_data["page"]

    batch_size = 100
    context["batch_size"] = batch_size
    context["page"] = page

    start = (page - 1) * batch_size
    end = start + batch_size

    context["total_count"] = qs.count()

    qs = qs.values(
        "id",
        "symbol",
        "debugid",
        "filename",
        "code_file",
        "code_id",
        "count",
        "modified_at",
        "created_at",
    )

    context["records"] = list(qs[start:end])

    return http.JsonResponse(context)
