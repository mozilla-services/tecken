# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import csv
import datetime
import gzip
import os
from urllib.parse import urlparse
from io import StringIO

import pytest
import mock
from markus import INCR

from django.utils import timezone
from django.urls import reverse
from django.db import OperationalError
from django.core.cache import caches

from tecken.base.symboldownloader import SymbolDownloader
from tecken.download import views
from tecken.download.models import MissingSymbol, MicrosoftDownload
from tecken.download.tasks import (
    download_microsoft_symbol,
    store_missing_symbol_task,
    DumpSymsError,
)
from tecken.download.utils import store_missing_symbol
from tecken.upload.models import FileUpload


_here = os.path.dirname(__file__)
# Remember, when you cabextract this file it will always create
# a file called 'ksproxy.pdb'. Even if you rename 'ksproxy.pd_' to
# something else.
PD__FILE = os.path.join(_here, "ksproxy.pd_")
FAKE_BROKEN_DUMP_SYMS = os.path.join(_here, "broken_dump_syms.sh")


def reload_downloaders(urls, try_downloader=None):
    """Because the tecken.download.views module has a global instance
    of SymbolDownloader created at start-up, it's impossible to easily
    change the URL if you want to test clients with a different URL.
    This function hotfixes that instance to use a different URL(s).
    """
    if isinstance(urls, str):
        urls = tuple([urls])
    views.normal_downloader = SymbolDownloader(urls)
    if try_downloader:
        views.try_downloader = SymbolDownloader([try_downloader])


def test_client_happy_path(client, gcsmock, metricsmock):
    reload_downloaders("https://storage.googleapis.example.com/private/prefix/")

    mock_bucket = gcsmock.MockBucket()

    def mock_get_bucket(bucket_name):
        assert bucket_name == "private"
        return mock_bucket

    gcsmock.get_bucket = mock_get_bucket

    def mock_get_blob(key):
        if key == "prefix/v0/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym":
            # As if it exists happily
            blob = gcsmock.mock_blob_factory(key)
            blob.public_url = "https://googleapis.example.com/private/" + key
            return blob

        raise NotImplementedError(key)

    mock_bucket.get_blob = mock_get_blob

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    response = client.get(url)
    assert response.status_code == 302
    parsed = urlparse(response["location"])
    assert parsed.netloc == "googleapis.example.com"
    # the pre-signed URL will have the bucket in the path
    assert parsed.path == (
        "/private/prefix/v0/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
    )
    response = client.head(url)
    assert response.status_code == 200
    assert response.content == b""

    assert response["Access-Control-Allow-Origin"] == "*"
    assert response["Access-Control-Allow-Methods"] == "GET"


def test_client_happy_path_s3(client, botomock, metricsmock, settings):
    reload_downloaders("https://s3.example.com/private/prefix/")

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 302
        parsed = urlparse(response["location"])
        assert parsed.netloc == "s3.example.com"
        # the pre-signed URL will have the bucket in the path
        assert parsed.path == (
            "/private/prefix/v0/" "xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
        )
        assert "Signature=" in parsed.query
        assert "Expires=" in parsed.query
        assert "AWSAccessKeyId=" in parsed.query

        response = client.head(url)
        assert response.status_code == 200
        assert response.content == b""

        assert response["Access-Control-Allow-Origin"] == "*"
        assert response["Access-Control-Allow-Methods"] == "GET"


def test_client_legacy_product_prefix(client, gcsmock, metricsmock):
    reload_downloaders("https://storage.googleapis.example.com/private/prefix/")

    mock_bucket = gcsmock.MockBucket()

    gcsmock.get_bucket = lambda name: mock_bucket

    def mock_get_blob(key):
        if key == "prefix/v0/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym":
            # As if it exists happily
            blob = gcsmock.mock_blob_factory(key)
            blob.public_url = "https://googleapis.example.com/private/" + key
            return blob

        raise NotImplementedError(key)

    mock_bucket.get_blob = mock_get_blob

    url = reverse(
        "download:download_symbol_legacy",
        args=("firefox", "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    response = client.get(url)
    assert response.status_code == 302
    parsed = urlparse(response["location"])
    assert parsed.netloc == "googleapis.example.com"
    # the pre-signed URL will have the bucket in the path
    assert parsed.path == (
        "/private/prefix/v0/" "xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
    )

    response = client.head(url)
    assert response.status_code == 200
    assert response.content == b""

    assert response["Access-Control-Allow-Origin"] == "*"
    assert response["Access-Control-Allow-Methods"] == "GET"

    # But if you try to mess with the prefix to something NOT
    # recognized, it should immediately 404.
    url = reverse(
        "download:download_symbol_legacy",
        args=("gobblygook", "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_client_try_download(client, gcsmock, settings):
    """Suppose there's a file that doesn't exist in any of the
    settings.SYMBOL_URLS but does exist in settings.UPLOAD_TRY_SYMBOLS_URL,
    then to reach that file you need to use ?try on the URL.
    """
    reload_downloaders(
        "https://storage.googleapis.example.com/private/prefix/",
        try_downloader="https://storage.googleapis.example.com/private/trying",
    )
    mock_calls = []

    mock_bucket = gcsmock.MockBucket()

    def mock_get_bucket(name):
        mock_bucket.name = name
        return mock_bucket

    gcsmock.get_bucket = mock_get_bucket

    def mock_get_blob(key):
        mock_calls.append(key)
        if key == "prefix/v0/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym":
            return None
        if key == "trying/v0/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym":
            # As if it exists happily
            blob = gcsmock.mock_blob_factory(key)
            # blob.public_url = "https://googleapis.example.com/trying/" + key
            return blob

        raise NotImplementedError(key)

    mock_bucket.get_blob = mock_get_blob
    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    try_url = reverse(
        "download:download_symbol_try",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    response = client.get(url)
    assert response.status_code == 404
    assert len(mock_calls) == 1

    response = client.get(try_url)
    assert response.status_code == 302
    assert len(mock_calls) == 2
    # Also note that the headers are the same as for regular downloads
    assert response["Access-Control-Allow-Origin"] == "*"
    # And like regular download, you're only allowed to use GET or HEAD
    response = client.put(try_url)
    assert response.status_code == 405
    # And calling it with DEBUG header should return a header with
    # some debug info. Just like regular download.
    response = client.get(try_url, HTTP_DEBUG="true")
    assert response.status_code == 302
    assert float(response["debug-time"]) > 0

    # You can also use the regular URL but add ?try to the URL
    response = client.get(url, {"try": True})
    assert response.status_code == 302
    assert len(mock_calls) == 2

    # Do it again, to make sure the caches work in our favor
    response = client.get(url)
    assert response.status_code == 404
    assert len(mock_calls) == 2

    response = client.get(try_url)
    assert response.status_code == 302
    assert len(mock_calls) == 2


@pytest.mark.django_db
def test_client_try_download_s3(client, botomock, settings):
    """Suppose there's a file that doesn't exist in any of the
    settings.SYMBOL_URLS but does exist in settings.UPLOAD_TRY_SYMBOLS_URL,
    then to reach that file you need to use ?try on the URL.
    """
    reload_downloaders(
        "https://s3.example.com/private",
        try_downloader="https://s3.example.com/private/trying",
    )

    mock_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        mock_calls.append(api_params)
        if api_params["Prefix"].startswith("trying/v0/"):
            # Yeah, we have it
            return {"Contents": [{"Key": api_params["Prefix"]}]}
        elif api_params["Prefix"].startswith("v0"):
            # Pretned nothing was returned. Ie. 404
            return {}
        else:
            raise NotImplementedError(api_params["Prefix"])

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    try_url = reverse(
        "download:download_symbol_try",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 404
        assert len(mock_calls) == 1

        response = client.get(try_url)
        assert response.status_code == 302
        assert len(mock_calls) == 2
        # Also note that the headers are the same as for regular downloads
        assert response["Access-Control-Allow-Origin"] == "*"
        # And like regular download, you're only allowed to use GET or HEAD
        response = client.put(try_url)
        assert response.status_code == 405
        # And calling it with DEBUG header should return a header with
        # some debug info. Just like regular download.
        response = client.get(try_url, HTTP_DEBUG="true")
        assert response.status_code == 302
        assert float(response["debug-time"]) > 0

        # You can also use the regular URL but add ?try to the URL
        response = client.get(url, {"try": True})
        assert response.status_code == 302
        assert len(mock_calls) == 2

        # Do it again, to make sure the caches work in our favor
        response = client.get(url)
        assert response.status_code == 404
        assert len(mock_calls) == 2

        response = client.get(try_url)
        assert response.status_code == 302
        assert len(mock_calls) == 2


def test_client_with_debug(client, botomock, metricsmock):
    reload_downloaders("https://s3.example.com/private/prefix/")

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        if api_params["Prefix"].endswith("xil.sym"):
            return {"Contents": []}
        elif api_params["Prefix"].endswith("xul.sym"):
            return {"Contents": [{"Key": api_params["Prefix"]}]}
        else:
            raise NotImplementedError(api_params)

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    with botomock(mock_api_call):
        response = client.get(url, HTTP_DEBUG="true")
        assert response.status_code == 302
        parsed = urlparse(response["location"])
        assert float(response["debug-time"]) > 0
        assert parsed.netloc == "s3.example.com"
        # the pre-signed URL will have the bucket in the path
        assert parsed.path == (
            "/private/prefix/v0/" "xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
        )
        assert "Signature=" in parsed.query
        assert "Expires=" in parsed.query
        assert "AWSAccessKeyId=" in parsed.query

        response = client.head(url, HTTP_DEBUG="true")
        assert response.status_code == 200
        assert response.content == b""
        assert float(response["debug-time"]) > 0

        # This one won't be logged because the filename is on a blacklist
        # of symbol filenames to ignore
        ignore_url = reverse(
            "download:download_symbol",
            args=("cxinjime.pdb", "342D9B0A3AE64812A2388C055C9F6C321", "file.ptr"),
        )
        response = client.get(ignore_url, HTTP_DEBUG="true")
        assert response.status_code == 404
        assert float(response["debug-time"]) == 0.0

        # Do a GET with a file that doesn't exist.
        not_found_url = reverse(
            "download:download_symbol",
            args=("xil.pdb", "55F4EC8C2F41492B9369D6B9A059577A1", "xil.sym"),
        )
        response = client.get(not_found_url, HTTP_DEBUG="true")
        assert response.status_code == 404
        assert float(response["debug-time"]) > 0


def test_client_with_ignorable_file_extensions(client, botomock):
    def mock_api_call(self, operation_name, api_params):
        assert False, "This mock function shouldn't be called"

    url = reverse(
        "download:download_symbol",
        args=(
            "xul.pdb",
            "44E4EC8C2F41492B9369D6B9A059577C2",
            # Note! This is NOT in the settings.DOWNLOAD_FILE_EXTENSIONS_WHITELIST
            # list.
            "xul.xxx",
        ),
    )
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 404


def test_client_with_debug_with_cache(client, botomock, metricsmock):
    reload_downloaders("https://s3.example.com/private/prefix/")

    mock_api_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        mock_api_calls.append(api_params)
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    with botomock(mock_api_call):
        response = client.get(url, HTTP_DEBUG="true")
        assert response.status_code == 302
        assert float(response["debug-time"]) > 0

        response = client.get(url, HTTP_DEBUG="true")
        assert response.status_code == 302
        assert float(response["debug-time"]) > 0

        response = client.head(url, HTTP_DEBUG="true")
        assert response.status_code == 200
        assert float(response["debug-time"]) > 0

        assert len(mock_api_calls) == 1


def test_client_with_cache_refreshed(client, botomock, metricsmock):
    reload_downloaders("https://s3.example.com/private/prefix/")

    mock_api_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        mock_api_calls.append(api_params)
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 302
        assert len(mock_api_calls) == 1

        response = client.get(url)
        assert response.status_code == 302
        assert len(mock_api_calls) == 1  # still 1

        response = client.get(url, {"_refresh": 1})
        assert response.status_code == 302
        assert len(mock_api_calls) == 2


def test_client_404(client, botomock, clear_redis_store):
    reload_downloaders("https://s3.example.com/private/prefix/")

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        return {}

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 404
        assert "Symbol Not Found" in response.content.decode("utf-8")

        response = client.head(url)
        assert response.status_code == 404


@pytest.mark.django_db
def test_client_404_logged(client, botomock, clear_redis_store, settings):
    reload_downloaders("https://s3.example.com/private/prefix/")

    settings.ENABLE_STORE_MISSING_SYMBOLS = True

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        return {}

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    with botomock(mock_api_call):
        assert client.get(url).status_code == 404
        assert client.get(url).status_code == 404
        # This one won't be logged because it's a HEAD
        assert client.head(url).status_code == 404

        # This one won't be logged because the filename is on a blacklist
        # of symbol filenames to ignore
        ignore_url = reverse(
            "download:download_symbol",
            args=("cxinjime.pdb", "342D9B0A3AE64812A2388C055C9F6C321", "file.ptr"),
        )
        response = client.get(ignore_url)
        assert response.status_code == 404
        assert response.content == b"Symbol Not Found (and ignored)"

        # This one won't be logged either
        ignore_url = reverse(
            "download:download_symbol",
            args=("cxinjime.pdb", "000000000000000000000000000000000", "cxinjime.sym"),
        )
        response = client.get(ignore_url)
        assert response.status_code == 404
        assert response.content == b"Symbol Not Found (and ignored)"

        # This "should" have logged the missing symbols twice.
        # Actually it shouldn't log it twice because the work on logging
        # missing symbols is guarded by a memoizer that prevents it from
        # executing more than once per arguments.
        assert MissingSymbol.objects.all().count() == 1
        assert MissingSymbol.objects.get(
            symbol="xul.pdb",
            debugid="44E4EC8C2F41492B9369D6B9A059577C2",
            filename="xul.sym",
            code_file__isnull=True,
            code_id__isnull=True,
        )

        # Now look it up with ?code_file= and ?code_id= etc.
        assert client.get(url, {"code_file": "xul.dll"}).status_code == 404
        assert client.get(url, {"code_id": "deadbeef"}).status_code == 404
        # both
        assert (
            client.get(url, {"code_file": "xul.dll", "code_id": "deadbeef"}).status_code
            == 404
        )

        assert MissingSymbol.objects.all().count() == 4
        assert MissingSymbol.objects.get(
            symbol="xul.pdb",
            debugid="44E4EC8C2F41492B9369D6B9A059577C2",
            filename="xul.sym",
            # The one with both set to something.
            code_file="xul.dll",
            code_id="deadbeef",
        )


@pytest.mark.django_db
def test_client_404_logged_bad_code_file(client, botomock, clear_redis_store, settings):
    """The root of this test is to test something that's been observed
    to happen in production; query strings for missing symbols with
    values that contain URL encoded nullbytes (%00).
    """
    reload_downloaders("https://s3.example.com/private/prefix/")

    settings.ENABLE_STORE_MISSING_SYMBOLS = True

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        return {}

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    with botomock(mock_api_call):
        params = {"code_file": "\x00"}
        assert client.head(url, params).status_code == 404
        assert client.get(url, params).status_code == 400

        # It won't get logged
        assert not MissingSymbol.objects.all().exists()

        # Same thing to happen if the 'code_id' contains nullbytes
        params = {"code_id": "Nice\x00Try"}
        assert client.head(url, params).status_code == 404
        assert client.get(url, params).status_code == 400
        assert not MissingSymbol.objects.all().exists()


def test_log_symbol_get_404_metrics(metricsmock):
    views.log_symbol_get_404(
        "xul.pdb",
        "44E4EC8C2F41492B9369D6B9A059577C2",
        "xul.sym",
        code_file="",
        code_id="",
    )
    records = metricsmock.get_records()
    assert len(records) == 1

    # Call it again with the exact same parameters
    views.log_symbol_get_404(
        "xul.pdb",
        "44E4EC8C2F41492B9369D6B9A059577C2",
        "xul.sym",
        code_file="",
        code_id="",
    )
    records = metricsmock.get_records()
    assert len(records) == 1  # unchanged

    # change one parameter slightly
    views.log_symbol_get_404(
        "xul.pdb",
        "44E4EC8C2F41492B9369D6B9A059577C2",
        "xul.sym",
        code_file="",
        code_id="deadbeef",
    )
    records = metricsmock.get_records()
    assert len(records) == 2  # changed


@pytest.mark.django_db
def test_missing_symbols_csv(client, settings):
    settings.ENABLE_STORE_MISSING_SYMBOLS = True

    url = reverse("download:missing_symbols_csv")
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-type"] == "text/csv"
    today = timezone.now()
    yesterday = today - datetime.timedelta(days=1)
    expect_filename = yesterday.strftime("missing-symbols-%Y-%m-%d.csv")
    assert expect_filename in response["Content-Disposition"]

    lines = response.content.splitlines()
    assert lines == [b"debug_file,debug_id,code_file,code_id"]

    # Log at least one line
    views.log_symbol_get_404(
        "xul.pdb",
        "44E4EC8C2F41492B9369D6B9A059577C2",
        "xul.sym",
        code_file="xul.dll",
        code_id="deadbeef",
    )
    views.log_symbol_get_404(
        "rooksdol_x64.dll",
        "58B6E33D262000",
        "rooksdol_x64.dl_",
        code_file="",
        code_id="",
    )

    # It's empty because it reports for yesterday, but we made the
    # only log today.
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    reader = csv.reader(StringIO(content))
    lines_of_lines = list(reader)
    assert len(lines_of_lines) == 2
    line = lines_of_lines[1]
    assert line[0] == "xul.pdb"
    assert line[1] == "44E4EC8C2F41492B9369D6B9A059577C2"
    assert line[2] == "xul.dll"
    assert line[3] == "deadbeef"


def test_get_microsoft_symbol_client(client, botomock, settings):
    settings.ENABLE_DOWNLOAD_FROM_MICROSOFT = True
    reload_downloaders("https://s3.example.com/private/prefix/")

    mock_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        mock_calls.append(api_params["Prefix"])
        return {}

    url = reverse(
        "download:download_symbol",
        args=("foo.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "foo.sym"),
    )

    task_arguments = []

    def fake_task(symbol, debugid, **kwargs):
        task_arguments.append((symbol, debugid, kwargs))

    _mock_function = "tecken.download.views.download_microsoft_symbol.delay"
    with mock.patch(_mock_function, new=fake_task):
        with botomock(mock_api_call):
            response = client.get(url)
            assert response.status_code == 404
            assert response.content == b"Symbol Not Found Yet"
            assert task_arguments
            task_argument, = task_arguments
            assert task_argument[0] == "foo.pdb"
            assert task_argument[1] == "44E4EC8C2F41492B9369D6B9A059577C2"

            # Pretend we're excessively eager
            response = client.get(url)
            assert response.status_code == 404
            assert response.content == b"Symbol Not Found Yet"

            # This basically checks that the SymbolDownloader cache is
            # not invalidated between calls.
            assert len(mock_calls) == 1
            # However, the act of triggering that
            # download_microsoft_symbol.delay() call is guarded by a
            # cache. So it shouldn't have called it more than
            # once.
            assert len(task_arguments) == 1


@pytest.mark.django_db
def test_store_missing_symbol_task_happy_path():
    store_missing_symbol_task("foo.pdb", "HEX", "foo.sym", code_file="file")
    assert MissingSymbol.objects.get(
        symbol="foo.pdb",
        debugid="HEX",
        filename="foo.sym",
        code_file="file",
        code_id__isnull=True,
    )


@pytest.mark.django_db
def test_download_microsoft_symbol_task_happy_path(gcsmock, metricsmock, requestsmock):
    with open(PD__FILE, "rb") as f:
        content = f.read()
        # just checking that the fixture file is sane
        assert content.startswith(b"MSCF")
        requestsmock.get(
            "https://msdl.microsoft.com/download/symbols/ksproxy.pdb"
            "/A7D6F1BB18CD4CB48/ksproxy.pd_",
            content=content,
        )

    mock_bucket = gcsmock.MockBucket()

    def mock_get_bucket(bucket_name):
        assert bucket_name == "private"
        return mock_bucket

    gcsmock.get_bucket = mock_get_bucket

    def mock_get_blob(key):
        if key == "v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym":
            # As if it doesn't exist
            return None
        raise NotImplementedError(key)

    mock_bucket.get_blob = mock_get_blob

    files_uploaded = []

    def mocked_create_blob(key):
        if key == "v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym":
            blob = gcsmock.MockBlob(key)

            def mock_upload_from_file(file):
                files_uploaded.append(key)
                content = file.read()
                assert isinstance(content, bytes)
                # We know what the expected size is based on having run:
                #   $ cabextract ksproxy.pd_
                #   $ dump_syms ksproxy.pdb > ksproxy.sym
                #   $ ls -l ksproxy.sym
                #   1721
                assert len(content) == 729
                original_content = gzip.decompress(content)
                assert len(original_content) == 1721

            blob.upload_from_file = mock_upload_from_file
            return blob

        raise NotImplementedError(key)

    mock_bucket.blob = mocked_create_blob

    symbol = "ksproxy.pdb"
    debugid = "A7D6F1BB18CD4CB48"
    download_microsoft_symbol(symbol, debugid)

    assert files_uploaded == ["v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym"]

    # The ultimate test is that it should have created a file_upload
    file_upload, = FileUpload.objects.all()
    assert file_upload.size == 729
    assert file_upload.bucket_name == "private"
    assert file_upload.key == "v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym"
    assert not file_upload.update
    assert not file_upload.upload
    assert file_upload.compressed
    assert file_upload.completed_at
    assert file_upload.microsoft_download

    # It should also have created a MicrosoftDownload record.
    download_obj, = MicrosoftDownload.objects.all()
    assert download_obj.completed_at
    assert download_obj.skipped is False
    assert download_obj.error is None

    # Check that markus caught timings of the individual file processing
    records = metricsmock.get_records()
    assert len(records) == 10
    assert records[0][1] == "tecken.download_store_missing_symbol"
    assert records[1][1] == "tecken.download_cabextract"
    assert records[2][1] == "tecken.download_dump_syms"
    assert records[3][1] == "tecken.upload_file_exists"
    assert records[4][1] == "tecken.upload_gzip_payload"
    assert records[5][1] == "tecken.upload_put_object"
    assert records[6][1] == "tecken.upload_file_upload_upload"
    assert records[7][1] == "tecken.upload_file_upload"
    assert records[8][1] == ("tecken.download_microsoft_download_file_upload_upload")
    assert records[9][1] == "tecken.download_upload_microsoft_symbol"


@pytest.mark.django_db
def test_download_microsoft_symbol_task_skipped(gcsmock, metricsmock, requestsmock):
    with open(PD__FILE, "rb") as f:
        content = f.read()
        # just checking that the fixture file is sane
        assert content.startswith(b"MSCF")
        requestsmock.get(
            "https://msdl.microsoft.com/download/symbols/ksproxy.pdb"
            "/A7D6F1BB18CD4CB48/ksproxy.pd_",
            content=content,
        )

    mock_bucket = gcsmock.MockBucket()

    def mock_get_bucket(bucket_name):
        assert bucket_name == "private"
        return mock_bucket

    gcsmock.get_bucket = mock_get_bucket

    def mock_get_blob(key):
        if key == "v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym":
            return gcsmock.mock_blob_factory(key, size=729)
        raise NotImplementedError(key)

    mock_bucket.get_blob = mock_get_blob

    def mocked_create_blob(key):
        # Nothing should be uploaded.
        raise NotImplementedError(key)

    mock_bucket.blob = mocked_create_blob

    symbol = "ksproxy.pdb"
    debugid = "A7D6F1BB18CD4CB48"
    download_microsoft_symbol(symbol, debugid)

    download_obj, = MicrosoftDownload.objects.all()
    assert not download_obj.error
    assert download_obj.skipped
    assert download_obj.completed_at

    # The ultimate test is that it should NOT have created a file upload.
    assert not FileUpload.objects.all().exists()

    # Check that markus caught timings of the individual file processing
    metricsmock.has_record(INCR, "tecken.microsoft_download_file_upload_skip", 1, None)


@pytest.mark.django_db
def test_download_microsoft_symbol_task_not_found(gcsmock, metricsmock, requestsmock):
    requestsmock.get(
        "https://msdl.microsoft.com/download/symbols/ksproxy.pdb"
        "/A7D6F1BB18CD4CB48/ksproxy.pd_",
        content=b"Page Not Found",
        status_code=404,
    )

    symbol = "ksproxy.pdb"
    debugid = "A7D6F1BB18CD4CB48"
    download_microsoft_symbol(symbol, debugid)
    assert not FileUpload.objects.all().exists()
    assert not MicrosoftDownload.objects.all().exists()


@pytest.mark.django_db
def test_download_microsoft_symbol_task_wrong_file_header(
    gcsmock, metricsmock, requestsmock
):
    requestsmock.get(
        "https://msdl.microsoft.com/download/symbols/ksproxy.pdb"
        "/A7D6F1BB18CD4CB48/ksproxy.pd_",
        content=b"some other junk",
    )

    symbol = "ksproxy.pdb"
    debugid = "A7D6F1BB18CD4CB48"
    download_microsoft_symbol(symbol, debugid)
    assert not FileUpload.objects.all().exists()

    download_obj, = MicrosoftDownload.objects.all()
    assert "did not start with 'MSCF'" in download_obj.error


@pytest.mark.django_db
def test_download_microsoft_symbol_task_cabextract_failing(
    gcsmock, metricsmock, requestsmock
):
    requestsmock.get(
        "https://msdl.microsoft.com/download/symbols/ksproxy.pdb"
        "/A7D6F1BB18CD4CB48/ksproxy.pd_",
        content=b"MSCF but not a real binary",
    )

    symbol = "ksproxy.pdb"
    debugid = "A7D6F1BB18CD4CB48"
    download_microsoft_symbol(symbol, debugid)
    assert not FileUpload.objects.all().exists()

    download_obj, = MicrosoftDownload.objects.all()
    assert "cabextract failed" in download_obj.error


@pytest.mark.django_db
def test_download_microsoft_symbol_task_dump_syms_failing(
    gcsmock, settings, metricsmock, requestsmock
):
    settings.DUMP_SYMS_PATH = FAKE_BROKEN_DUMP_SYMS

    with open(PD__FILE, "rb") as f:
        content = f.read()
        # just checking that the fixture file is sane
        assert content.startswith(b"MSCF")
        requestsmock.get(
            "https://msdl.microsoft.com/download/symbols/ksproxy.pdb"
            "/A7D6F1BB18CD4CB48/ksproxy.pd_",
            content=content,
        )

    symbol = "ksproxy.pdb"
    debugid = "A7D6F1BB18CD4CB48"
    with pytest.raises(DumpSymsError):
        download_microsoft_symbol(symbol, debugid)

    download_obj, = MicrosoftDownload.objects.all()
    assert "dump_syms extraction failed" in download_obj.error
    assert "Something horrible happened" in download_obj.error


@pytest.mark.django_db
def test_store_missing_symbol_happy_path(metricsmock):
    views.store_missing_symbol("foo.pdb", "ABCDEF12345", "foo.sym")
    missing_symbol = MissingSymbol.objects.get(
        symbol="foo.pdb",
        debugid="ABCDEF12345",
        filename="foo.sym",
        code_file__isnull=True,
        code_id__isnull=True,
    )
    assert missing_symbol.hash
    assert missing_symbol.count == 1
    first_modified_at = missing_symbol.modified_at

    # Repeat and it should increment
    views.store_missing_symbol("foo.pdb", "ABCDEF12345", "foo.sym")
    missing_symbol.refresh_from_db()
    assert missing_symbol.count == 2
    assert missing_symbol.modified_at > first_modified_at

    records = metricsmock.get_records()
    assert len(records) == 2
    assert records[0][1] == "tecken.download_store_missing_symbol"
    assert records[1][1] == "tecken.download_store_missing_symbol"

    # This time with a code_file and code_id
    views.store_missing_symbol(
        "foo.pdb",
        "ABCDEF12345",
        "foo.sym",
        code_file="libsystem_pthread.dylib",
        code_id="id",
    )
    second_missing_symbol = MissingSymbol.objects.get(
        symbol="foo.pdb",
        debugid="ABCDEF12345",
        filename="foo.sym",
        code_file="libsystem_pthread.dylib",
        code_id="id",
    )
    assert second_missing_symbol.hash != missing_symbol.hash
    assert second_missing_symbol.count == 1


@pytest.mark.django_db
def test_store_missing_symbol_skips(metricsmock):
    # If either symbol, debugid or filename are too long nothing is stored
    views.store_missing_symbol("x" * 200, "ABCDEF12345", "foo.sym")
    views.store_missing_symbol("foo.pdb", "x" * 200, "foo.sym")
    views.store_missing_symbol("foo.pdb", "ABCDEF12345", "x" * 200)
    assert not MissingSymbol.objects.all().exists()


@pytest.mark.django_db
def test_store_missing_symbol_skips_bad_code_file_or_id(metricsmock):
    # If the code_file or code_id is too long don't bother storing it.
    views.store_missing_symbol("foo.pdb", "ABCDEF12345", "foo.sym", code_file="x" * 200)
    views.store_missing_symbol("foo.pdb", "ABCDEF12345", "foo.sym", code_id="x" * 200)
    assert not MissingSymbol.objects.all().exists()


@pytest.mark.django_db
def test_store_missing_symbol_client(client, botomock, settings):
    settings.ENABLE_STORE_MISSING_SYMBOLS = True
    reload_downloaders("https://s3.example.com/private/prefix/")

    mock_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        mock_calls.append(api_params["Prefix"])
        return {}

    url = reverse(
        "download:download_symbol",
        args=("foo.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "foo.ex_"),
    )

    with botomock(mock_api_call):
        response = client.get(url, {"code_file": "something"})
        assert response.status_code == 404
        assert response.content == b"Symbol Not Found"
        assert MissingSymbol.objects.all().count() == 1

        # Pretend we're excessively eager
        response = client.get(url, {"code_file": "something"})
        assert response.status_code == 404
        assert response.content == b"Symbol Not Found"

        # This basically checks that the SymbolDownloader cache is
        # not invalidated between calls.
        assert len(mock_calls) == 1
        # However, the act of triggering that
        # store_missing_symbol() call is guarded by a
        # cache. So it shouldn't have called it more than
        # once.
        assert MissingSymbol.objects.filter(count=1).count() == 1


@pytest.mark.django_db
def test_store_missing_symbol_client_operationalerror(client, botomock, settings):
    """If the *storing* of a missing symbols causes an OperationalError,
    the main client that requests should still be a 404.
    On the inside, what we do is catch the operational error, and
    instead call out to a celery job that does it instead.

    This test is a bit cryptic. The S3 call is mocked. The calling of the
    'store_missing_symbol()' function (that is in 'downloads/views.py')
    is mocked. Lastly, the wrapped task function 'store_missing_symbol_task()'
    is also mocked (so we don't actually call out to Redis).
    Inside the mocked call to the celery task, we actually call the
    original 'tecken.download.utils.store_missing_symbol' function just to
    make sure the MissingSymbol record gets created.
    """
    settings.ENABLE_STORE_MISSING_SYMBOLS = True
    reload_downloaders("https://s3.example.com/private/prefix/")

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        return {}

    url = reverse(
        "download:download_symbol",
        args=("foo.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "foo.ex_"),
    )

    task_arguments = []

    def fake_task(*args, **kwargs):
        store_missing_symbol(*args, **kwargs)
        task_arguments.append(args)

    store_args = []

    def mock_store_missing_symbols(*args, **kwargs):
        store_args.append(args)
        raise OperationalError("On noes!")

    _mock_function = "tecken.download.views.store_missing_symbol_task.delay"
    with botomock(mock_api_call), mock.patch(
        "tecken.download.views.store_missing_symbol", new=mock_store_missing_symbols
    ), mock.patch(_mock_function, new=fake_task):
        response = client.get(url, {"code_file": "something"})
        assert response.status_code == 404
        assert response.content == b"Symbol Not Found"
        assert len(store_args) == 1
        assert len(task_arguments) == 1
        assert MissingSymbol.objects.all().count() == 1


def test_client_with_bad_filenames(client, botomock, metricsmock):
    reload_downloaders("https://s3.example.com/private/prefix/")

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        return {"Contents": []}

    with botomock(mock_api_call):
        url = reverse(
            "download:download_symbol",
            args=(
                "xül.pdb",  # <-- note the extended ascii char
                "44E4EC8C2F41492B9369D6B9A059577C2",
                "xul.sym",
            ),
        )
        response = client.get(url)
        assert response.status_code == 400

        url = reverse(
            "download:download_symbol",
            args=(
                "x%l.pdb",  # <-- note the %
                "44E4EC8C2F41492B9369D6B9A059577C2",
                "xul.sym",
            ),
        )
        response = client.get(url)
        assert response.status_code == 400

        url = reverse(
            "download:download_symbol",
            args=(
                "xul.pdb",
                "44E4EC8C2F41492B9369D6B9A059577C2",
                "xul#.ex_",  # <-- note the #
            ),
        )
        response = client.get(url)
        assert response.status_code == 400

        url = reverse(
            "download:download_symbol",
            args=(
                "crypt3\x10.pdb",
                "3D0443BF4FF5446B83955512615FD0942",
                "crypt3\x10.pd_",
            ),
        )
        response = client.get(url)
        assert response.status_code == 400

        # There are many more characters that can cause a 400 response
        # because the symbol or the filename contains, what's considered,
        # invalid characters. But there are some that actually work
        # that might be a bit surprising.
        url = reverse(
            "download:download_symbol",
            args=("汉.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
        )
        response = client.get(url)
        assert response.status_code == 404

        url = reverse(
            "download:download_symbol",
            args=("foo.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "⚡️.sym"),
        )
        response = client.get(url)
        assert response.status_code == 404

        url = reverse(
            "download:download_symbol",
            args=(
                "space in the filename.pdb",
                "44E4EC8C2F41492B9369D6B9A059577C2",
                "bar.ex_",
            ),
        )
        response = client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
def test_missingsymbol_model_counts():
    # The .total_count won't change just because you manually
    # create, edit, or delete MissingSymbol instances. The increments are
    # done explicitly in the code where upserts are made.
    assert MissingSymbol.total_count() == 0
    MissingSymbol.objects.create(
        hash="anything",
        symbol="xul.pdb",
        debugid="44E4EC8C2F41492B9369D6B9A059577C2",
        filename="xul.sym",
    )
    assert MissingSymbol.total_count() == 0

    # If you clear the cache, it will recalculate.
    caches["default"].clear()
    assert MissingSymbol.total_count() == 1

    MissingSymbol.incr_total_count()
    assert MissingSymbol.total_count() == 2


@pytest.mark.django_db
def test_missingsymbol_counts_by_upsert():
    # First, prime the cache
    assert MissingSymbol.total_count() == 0

    store_missing_symbol_task("foo.pdb", "HEX", "foo.sym", code_file="file")
    assert MissingSymbol.total_count() == 1

    store_missing_symbol_task("foo.pdb", "HEX", "foo.sym", code_file="file")
    assert MissingSymbol.total_count() == 1

    store_missing_symbol_task("foo.pdb", "HEX2", "foo.sym", code_file="file")
    assert MissingSymbol.total_count() == 2
