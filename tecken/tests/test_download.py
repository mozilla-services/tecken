# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
from urllib.parse import urlparse

from django.urls import reverse

from tecken.base.symboldownloader import SymbolDownloader
from tecken.download import views
from tecken.upload.models import FileUpload


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

    debugfilename = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    symfile = "xul.sym"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{debugfilename}/{debugid}/{symfile}",
        data=b"abc123",
    )

    url = reverse("download:download_symbol", args=(debugfilename, debugid, symfile))

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

    debugfilename = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    symfile = "xul.sym"

    # Upload a file into the try bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"try/v1/{debugfilename}/{debugid}/{symfile}",
        data=b"abc123",
    )

    url = reverse("download:download_symbol", args=(debugfilename, debugid, symfile))
    response = client.get(url)
    assert response.status_code == 404

    try_url = reverse(
        "download:download_symbol_try", args=(debugfilename, debugid, symfile)
    )
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

    debugfilename = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    symfile = "xul.sym"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{debugfilename}/{debugid}/{symfile}",
        data=b"abc123",
    )

    # Do a GET request which returns the redirect url
    url = reverse("download:download_symbol", args=(debugfilename, debugid, symfile))
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

    debugfilename = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    symfile = "xul.sym"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{debugfilename}/{debugid}/{symfile}",
        data=b"abc123",
    )

    url = reverse("download:download_symbol", args=(debugfilename, debugid, symfile))

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

    debugfilename = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    symfile = "xul.sym"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{debugfilename}/{debugid}/{symfile}",
        data=b"abc123",
    )

    url = reverse("download:download_symbol", args=(debugfilename, debugid, symfile))
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


def test_get_code_id_lookup(client, db, s3_helper):
    reload_downloaders(
        os.environ["UPLOAD_DEFAULT_URL"],
        try_downloader=os.environ["UPLOAD_TRY_SYMBOLS_URL"],
    )

    sym_file = "xul.sym"
    debug_filename = "xul.pdb"
    debug_id = "404B9729BE96C3CF4C4C44205044422E1"
    code_file = "xul.dll"
    code_id = "64E130A115A30000"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{debug_filename}/{debug_id}/{sym_file}",
        data=b"abc123",
    )
    FileUpload.objects.create(
        bucket_name="publicbucket",
        key=f"v1/{debug_filename}/{debug_id}/{sym_file}",
        size=100,
        debug_filename=debug_filename,
        debug_id=debug_id,
        code_file=code_file,
        code_id=code_id,
    )

    # Try normal download API url
    url = reverse(
        "download:download_symbol",
        args=(debug_filename, debug_id, sym_file),
    )
    response = client.get(url)
    assert response.status_code == 302

    # Try with code_file/code_id
    url = reverse(
        "download:download_symbol",
        args=(code_file, code_id, sym_file),
    )
    response = client.get(url)
    assert response.status_code == 302
    parsed = urlparse(response["location"])
    assert parsed.path == f"/{debug_filename}/{debug_id}/{sym_file}"

    # Try with querystring params
    response = client.get(url, {"code_file": code_file, "code_id": code_id})
    assert response.status_code == 302
    parsed = urlparse(response["location"])
    assert parsed.path == f"/{debug_filename}/{debug_id}/{sym_file}"
    assert parsed.query == f"code_file={code_file}&code_id={code_id}"


def test_head_code_id_lookup(client, db, s3_helper):
    reload_downloaders(
        os.environ["UPLOAD_DEFAULT_URL"],
        try_downloader=os.environ["UPLOAD_TRY_SYMBOLS_URL"],
    )

    sym_file = "xul.sym"
    debug_filename = "xul.pdb"
    debug_id = "404B9729BE96C3CF4C4C44205044422E1"
    code_file = "xul.dll"
    code_id = "64E130A115A30000"

    # Upload a file into the regular bucket
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{debug_filename}/{debug_id}/{sym_file}",
        data=b"abc123",
    )
    FileUpload.objects.create(
        bucket_name="publicbucket",
        key=f"v1/{debug_filename}/{debug_id}/{sym_file}",
        size=100,
        debug_filename=debug_filename,
        debug_id=debug_id,
        code_file=code_file,
        code_id=code_id,
    )

    # Try regular download API returns 200
    url = reverse(
        "download:download_symbol",
        args=(debug_filename, debug_id, sym_file),
    )
    response = client.head(url)
    assert response.status_code == 200

    # Try with code_file/code_id returns 302 redirect
    url = reverse(
        "download:download_symbol",
        args=(code_file, code_id, sym_file),
    )
    response = client.head(url)
    assert response.status_code == 302
    parsed = urlparse(response["location"])
    assert parsed.path == f"/{debug_filename}/{debug_id}/{sym_file}"

    # Try with querystring
    url = reverse(
        "download:download_symbol",
        args=(code_file, code_id, sym_file),
    )
    response = client.head(url, {"code_file": code_file, "code_id": code_id})
    assert response.status_code == 302
    parsed = urlparse(response["location"])
    assert parsed.path == f"/{debug_filename}/{debug_id}/{sym_file}"
    assert parsed.query == f"code_file={code_file}&code_id={code_id}"
