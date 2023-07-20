# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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


def test_client_happy_path(client, db, s3_helper):
    reload_downloaders(
        os.environ["UPLOAD_DEFAULT_URL"],
        try_downloader=os.environ["UPLOAD_TRY_SYMBOLS_URL"],
    )

    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{module}/{debugid}/{debugfn}",
        data=b"abc123",
    )

    url = reverse("download:download_symbol", args=(module, debugid, debugfn))

    response = client.get(url)
    assert response.status_code == 302
    parsed = urlparse(response["location"])
    assert parsed.netloc == "localstack:4566"

    assert parsed.path == (
        "/publicbucket/v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
    )

    response = client.head(url)
    assert response.status_code == 200

    assert response["Access-Control-Allow-Origin"] == "*"
    assert response["Access-Control-Allow-Methods"] == "GET"


def test_client_try_download(client, db, s3_helper):
    """Suppose there's a file that doesn't exist in any of the
    settings.SYMBOL_URLS but does exist in settings.UPLOAD_TRY_SYMBOLS_URL,
    then to reach that file you need to use ?try on the URL.

    """
    reload_downloaders(
        os.environ["UPLOAD_DEFAULT_URL"],
        try_downloader=os.environ["UPLOAD_TRY_SYMBOLS_URL"],
    )

    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    # Upload a file into the try bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"try/v1/{module}/{debugid}/{debugfn}",
        data=b"abc123",
    )

    url = reverse("download:download_symbol", args=(module, debugid, debugfn))
    response = client.get(url)
    assert response.status_code == 404

    try_url = reverse("download:download_symbol_try", args=(module, debugid, debugfn))
    response = client.get(try_url)
    assert response.status_code == 302
    # Also note that the headers are the same as for regular downloads
    assert response["Access-Control-Allow-Origin"] == "*"

    # And like regular download, you're only allowed to use GET or HEAD
    response = client.put(try_url)
    assert response.status_code == 405

    # And calling it with DEBUG header should return a header with some debug info. Just
    # like regular download.
    response = client.get(try_url, HTTP_DEBUG="true")
    assert response.status_code == 302
    assert float(response["debug-time"]) > 0

    # You can also use the regular URL but add ?try to the URL
    response = client.get(url, {"try": True})
    assert response.status_code == 302


def test_client_with_debug(client, db, s3_helper):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{module}/{debugid}/{debugfn}",
        data=b"abc123",
    )

    # Do a GET request which returns the redirect url
    url = reverse("download:download_symbol", args=(module, debugid, debugfn))
    response = client.get(url, HTTP_DEBUG="true")
    assert response.status_code == 302
    parsed = urlparse(response["location"])
    assert float(response["debug-time"]) > 0
    assert parsed.netloc == "localstack:4566"
    assert parsed.path == (
        "/publicbucket/v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
    )

    # Try a HEAD request
    response = client.head(url, HTTP_DEBUG="true")
    assert response.status_code == 200
    assert response.content == b""
    assert float(response["debug-time"]) > 0

    # Try a symbol file that doesn't exist--this one won't be logged because the
    # filename is on a block list of symbol filenames to ignore
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


def test_client_with_ignorable_file_extensions(client, db, s3_helper):
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

    response = client.get(url)
    assert response.status_code == 404


def test_client_with_debug_with_cache(client, db, s3_helper):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{module}/{debugid}/{debugfn}",
        data=b"abc123",
    )

    url = reverse("download:download_symbol", args=(module, debugid, debugfn))

    response = client.get(url, HTTP_DEBUG="true")
    assert response.status_code == 302
    assert float(response["debug-time"]) > 0

    # FIXME(willkg): this doesn't verify that it came from cache
    response = client.get(url, HTTP_DEBUG="true")
    assert response.status_code == 302
    assert float(response["debug-time"]) > 0

    response = client.head(url, HTTP_DEBUG="true")
    assert response.status_code == 200
    assert float(response["debug-time"]) > 0


def test_client_with_cache_refreshed(client, db, s3_helper):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{module}/{debugid}/{debugfn}",
        data=b"abc123",
    )

    url = reverse("download:download_symbol", args=(module, debugid, debugfn))
    response = client.get(url)
    assert response.status_code == 302

    # FIXME(willkg): this doesn't verify that it came from cache
    response = client.get(url)
    assert response.status_code == 302

    response = client.get(url, {"_refresh": 1})
    assert response.status_code == 302


def test_client_404(client, db, s3_helper):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

    url = reverse(
        "download:download_symbol",
        args=("xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"),
    )
    response = client.get(url)
    assert response.status_code == 404
    assert "Symbol Not Found" in response.content.decode("utf-8")

    response = client.head(url)
    assert response.status_code == 404


def test_client_404_logged(client, db, settings):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

    settings.ENABLE_STORE_MISSING_SYMBOLS = True
    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    url = reverse("download:download_symbol", args=(module, debugid, debugfn))

    # Call it twice, but it only gets logged once
    assert client.get(url).status_code == 404
    assert client.get(url).status_code == 404

    assert MissingSymbol.objects.all().count() == 1
    assert MissingSymbol.objects.get(
        symbol=module,
        debugid=debugid,
        filename=debugfn,
        code_file__isnull=True,
        code_id__isnull=True,
    )


def test_client_404_head_not_logged(client, db, settings):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

    settings.ENABLE_STORE_MISSING_SYMBOLS = True
    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    url = reverse("download:download_symbol", args=(module, debugid, debugfn))

    # This one won't be logged because it's a HEAD
    assert client.head(url).status_code == 404
    assert MissingSymbol.objects.all().count() == 0


def test_client_404_blocklisted_not_logged(client, db, settings):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

    settings.ENABLE_STORE_MISSING_SYMBOLS = True
    module = "cxinjime.pdb"
    debugid = "342D9B0A3AE64812A2388C055C9F6C321"
    debugfn = "file.ptr"

    # This one won't be logged because the filename is on a block list
    # of symbol filenames to ignore
    ignore_url = reverse("download:download_symbol", args=(module, debugid, debugfn))
    response = client.get(ignore_url)
    assert response.status_code == 404
    assert response.content == b"Symbol Not Found (and ignored)"
    assert MissingSymbol.objects.all().count() == 0


def test_client_404_code_id_code_file(client, db, settings):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

    settings.ENABLE_STORE_MISSING_SYMBOLS = True
    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    url = reverse("download:download_symbol", args=(module, debugid, debugfn))

    # Now look it up with ?code_file= and ?code_id= etc.
    assert client.get(url, {"code_file": "xul.dll"}).status_code == 404
    assert client.get(url, {"code_id": "deadbeef"}).status_code == 404
    # both
    assert (
        client.get(url, {"code_file": "xul.dll", "code_id": "deadbeef"}).status_code
        == 404
    )

    # NOTE(willkg): This should only have 1 entry that merges all the details, but for
    # some reason gets 3. I'm removing the missing symbols bookkeeping at some point, so
    # I'm just going to leave this as is for now.
    assert MissingSymbol.objects.all().count() == 3


def test_client_404_logged_bad_code_file(client, db, settings):
    """The root of this test is to test something that's been observed
    to happen in production; query strings for missing symbols with
    values that contain URL encoded nullbytes (%00).
    """
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

    settings.ENABLE_STORE_MISSING_SYMBOLS = True
    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    url = reverse("download:download_symbol", args=(module, debugid, debugfn))
    params = {"code_file": "\x00"}
    assert client.head(url, params).status_code == 404
    assert client.get(url, params).status_code == 400

    # It won't get logged
    assert MissingSymbol.objects.all().count() == 0

    # Same thing to happen if the 'code_id' contains nullbytes
    params = {"code_id": "bad\x00codeid"}
    assert client.head(url, params).status_code == 404
    assert client.get(url, params).status_code == 400
    assert MissingSymbol.objects.all().exists() == 0


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


def test_missingsymbols_csv(client, db, settings):
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


def test_missingsymbols(client, db, settings):
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


def test_store_missing_symbol_happy_path(db, metricsmock):
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


def test_store_missing_symbol_skips(
    db,
):
    # If either symbol, debugid or filename are too long nothing is stored
    views.store_missing_symbol("x" * 200, "ABCDEF12345", "foo.sym")
    views.store_missing_symbol("foo.pdb", "x" * 200, "foo.sym")
    views.store_missing_symbol("foo.pdb", "ABCDEF12345", "x" * 200)
    assert not MissingSymbol.objects.all().exists()


def test_store_missing_symbol_skips_bad_code_file_or_id(db):
    # If the code_file or code_id is too long don't bother storing it.
    views.store_missing_symbol("foo.pdb", "ABCDEF12345", "foo.sym", code_file="x" * 200)
    views.store_missing_symbol("foo.pdb", "ABCDEF12345", "foo.sym", code_id="x" * 200)
    assert not MissingSymbol.objects.all().exists()


def test_store_missing_symbol_client(client, db, settings):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])
    settings.ENABLE_STORE_MISSING_SYMBOLS = True

    module = "foo.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "foo.ex_"

    url = reverse("download:download_symbol", args=(module, debugid, debugfn))

    response = client.get(url, {"code_file": "something"})
    assert response.status_code == 404
    assert response.content == b"Symbol Not Found"
    assert MissingSymbol.objects.all().count() == 1

    # Pretend we're excessively eager
    response = client.get(url, {"code_file": "something"})
    assert response.status_code == 404
    assert response.content == b"Symbol Not Found"

    # The act of triggering that store_missing_symbol() call is guarded by a cache. So
    # it shouldn't have called it more than once.
    assert MissingSymbol.objects.filter(count=1).count() == 1


def test_client_with_bad_filenames(client, db):
    reload_downloaders(os.environ["UPLOAD_DEFAULT_URL"])

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

    # There are many more characters that can cause a 400 response because the symbol or
    # the filename contains, what's considered, invalid characters. But there are some
    # that actually work that might be a bit surprising.
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
