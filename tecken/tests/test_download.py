# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import csv
import datetime
from io import StringIO
import json
import os
from unittest import mock
from urllib.parse import urlparse

import pytest

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from tecken.base.symboldownloader import SymbolDownloader
from tecken.download import views
from tecken.download.models import MissingSymbol


_here = os.path.dirname(__file__)


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


def test_client_happy_path(client, botomock):
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


def test_client_legacy_product_prefix(client, botomock):
    reload_downloaders("https://s3.example.com/private/prefix/")

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    url = reverse(
        "download:download_symbol_legacy",
        args=("firefox", "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
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

    with botomock(mock_api_call):
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
    with botomock(mock_api_call):
        response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_client_try_download(client, botomock):
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


def test_client_with_debug(client, botomock):
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

        # This one won't be logged because the filename is on a block list
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
            # Note! This is NOT in the settings.DOWNLOAD_FILE_EXTENSIONS_ALLOWED
            # list.
            "xul.xxx",
        ),
    )
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 404


def test_client_with_debug_with_cache(client, botomock):
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


def test_client_with_cache_refreshed(client, botomock):
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


def test_client_404(client, botomock):
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
def test_client_404_logged(client, botomock, settings):
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

        # This one won't be logged because the filename is on a block list
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
def test_client_404_logged_bad_code_file(client, botomock, settings):
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
def test_missingsymbols_csv(client, settings):
    settings.ENABLE_STORE_MISSING_SYMBOLS = True

    url = reverse("download:missingsymbols_csv")
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


@pytest.mark.django_db
def test_missingsymbols(client, settings):
    settings.ENABLE_STORE_MISSING_SYMBOLS = True

    # Empty db works fine
    url = reverse("download:missingsymbols")
    response = client.get(url)
    assert response.status_code == 200
    expected = {
        "batch_size": 100,
        "records": [],
        "order_by": {"reverse": True, "sort": "modified_at"},
        "page": 1,
        "total_count": 0,
    }
    assert json.loads(response.content.decode("utf-8")) == expected

    today = timezone.now()
    yesterday = today - datetime.timedelta(days=1)

    # Add a couple of missing symbols and set modified_at and created_at
    # correctly
    views.log_symbol_get_404(
        "xul.pdb",
        "44E4EC8C2F41492B9369D6B9A059577C2",
        "xul.sym",
        code_file="xul.dll",
        code_id="deadbeef",
    )
    date_1 = yesterday.replace(hour=1, minute=1, second=1, microsecond=0)
    MissingSymbol.objects.filter(symbol="xul.pdb").update(
        modified_at=date_1, created_at=date_1
    )
    date_1_str = date_1.strftime("%Y-%m-%dT%H:%M:%SZ")

    views.log_symbol_get_404(
        "rooksdol_x64.dll",
        "58B6E33D262000",
        "rooksdol_x64.dl_",
        code_file="",
        code_id="",
    )
    date_2 = yesterday.replace(hour=2, minute=1, second=1, microsecond=0)
    MissingSymbol.objects.filter(symbol="rooksdol_x64.dll").update(
        modified_at=date_2, created_at=date_2
    )
    date_2_str = date_2.strftime("%Y-%m-%dT%H:%M:%SZ")

    response = client.get(url)
    assert response.status_code == 200
    data = json.loads(response.content.decode("utf-8"))
    expected = {
        "batch_size": 100,
        "order_by": {"reverse": True, "sort": "modified_at"},
        "page": 1,
        "records": [
            {
                "id": mock.ANY,
                "code_file": None,
                "code_id": None,
                "count": 1,
                "created_at": date_2_str,
                "debugid": "58B6E33D262000",
                "filename": "rooksdol_x64.dl_",
                "modified_at": date_2_str,
                "symbol": "rooksdol_x64.dll",
            },
            {
                "id": mock.ANY,
                "code_file": "xul.dll",
                "code_id": "deadbeef",
                "count": 1,
                "created_at": date_1_str,
                "debugid": "44E4EC8C2F41492B9369D6B9A059577C2",
                "filename": "xul.sym",
                "modified_at": date_1_str,
                "symbol": "xul.pdb",
            },
        ],
        "total_count": 2,
    }
    assert data == expected


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
    assert records[0].key == "tecken.download_store_missing_symbol"
    assert records[1].key == "tecken.download_store_missing_symbol"

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
def test_store_missing_symbol_skips():
    # If either symbol, debugid or filename are too long nothing is stored
    views.store_missing_symbol("x" * 200, "ABCDEF12345", "foo.sym")
    views.store_missing_symbol("foo.pdb", "x" * 200, "foo.sym")
    views.store_missing_symbol("foo.pdb", "ABCDEF12345", "x" * 200)
    assert not MissingSymbol.objects.all().exists()


@pytest.mark.django_db
def test_store_missing_symbol_skips_bad_code_file_or_id():
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


def test_client_with_bad_filenames(client, botomock):
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
def test_cleanse_missingsymbol_delete_records():
    """cleanse_missingsymbol deletes appropriate records"""
    today = timezone.now()
    cutoff = today - datetime.timedelta(days=30)

    # Create a record for today
    MissingSymbol.objects.create(
        hash="1",
        symbol="xul.so",
        debugid="1",
        filename="xul.so",
    )

    # Create a record before the cutoff--since modified_at is an "auto_now"
    # field, we need to mock time
    with mock.patch("django.utils.timezone.now") as mock_now:
        mock_now.return_value = cutoff + datetime.timedelta(days=1)
        MissingSymbol.objects.create(
            hash="2",
            symbol="xul.so",
            debugid="2",
            filename="xul.so",
        )

    # Create a record after the cutoff
    with mock.patch("django.utils.timezone.now") as mock_now:
        mock_now.return_value = cutoff - datetime.timedelta(days=1)
        MissingSymbol.objects.create(
            hash="3",
            symbol="xul.so",
            debugid="3",
            filename="xul.so",
        )

    for sym in MissingSymbol.objects.all():
        print("1", sym, sym.hash, sym.modified_at)

    stdout = StringIO()
    call_command("cleanse_missingsymbol", dry_run=False, stdout=stdout)
    output = stdout.getvalue()
    assert "deleted missingsymbol=1" in output

    # Verify that the record that was deleted was the old one
    assert sorted(MissingSymbol.objects.values_list("hash", flat=True)) == ["1", "2"]


@pytest.mark.django_db
def test_cleanse_missingsymbol_delete_records_dry_run():
    """cleanse_missingsymbol dry-run doesn't delete records"""
    today = timezone.now()
    cutoff = today - datetime.timedelta(days=30)

    # Create a record for today
    MissingSymbol.objects.create(
        hash="1",
        symbol="xul.so",
        debugid="1",
        filename="xul.so",
    )

    # Create a record before the cutoff--since modified_at is an "auto_now"
    # field, we need to mock time
    with mock.patch("django.utils.timezone.now") as mock_now:
        mock_now.return_value = cutoff + datetime.timedelta(days=1)
        MissingSymbol.objects.create(
            hash="2",
            symbol="xul.so",
            debugid="2",
            filename="xul.so",
        )

    # Create a record after the cutoff
    with mock.patch("django.utils.timezone.now") as mock_now:
        mock_now.return_value = cutoff - datetime.timedelta(days=1)
        MissingSymbol.objects.create(
            hash="3",
            symbol="xul.so",
            debugid="3",
            filename="xul.so",
        )

    for sym in MissingSymbol.objects.all():
        print("1", sym, sym.hash, sym.modified_at)

    stdout = StringIO()
    call_command("cleanse_missingsymbol", dry_run=True, stdout=stdout)
    output = stdout.getvalue()
    assert "DRY RUN" in output
    assert "deleted missingsymbol=1" in output

    # Verify no records were deleted
    assert sorted(MissingSymbol.objects.values_list("hash", flat=True)) == [
        "1",
        "2",
        "3",
    ]
