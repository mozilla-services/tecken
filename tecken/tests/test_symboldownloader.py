# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pytest

from tecken.base.symboldownloader import (
    SymbolDownloader,
    check_url_head,
)


@pytest.mark.parametrize(
    "prefix, symbol, debugid, filename, expected",
    [
        (
            "v1",
            "xul.pdb",
            "44E4EC8C2F41492B9369D6B9A059577C2",
            "xul.sym",
            "v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        ),
        (
            "v1",
            "libc++abi.dylib",
            "43940F08B65E38888CD3C52398EB1CA10",
            "libc++abi.dylib.sym",
            "v1/libc%2B%2Babi.dylib/43940F08B65E38888CD3C52398EB1CA10/libc%2B%2Babi.dylib.sym",
        ),
    ],
)
def test_make_url_path(prefix, symbol, debugid, filename, expected):
    path = SymbolDownloader.make_url_path(
        prefix=prefix, symbol=symbol, debugid=debugid, filename=filename
    )
    assert path == expected


def test_check_url_head(s3_helper, settings):
    module = "xul.pdb"
    debugid = "44E4EC8C2F41492B9369D6B9A059577C2"
    debugfn = "xul.sym"

    # Upload a file into the regular bucket
    # NOTE(willkg): The information here needs to match SYMBOL_URLS[0]
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key=f"v1/{module}/{debugid}/{debugfn}",
        data=b"abc123",
    )

    good_key = SymbolDownloader.make_url_path(
        prefix="v1",
        symbol=module,
        debugid=debugid,
        filename=debugfn,
    )
    bad_key = SymbolDownloader.make_url_path(
        prefix="v1",
        symbol="XUL",
        debugid="4C4C445955553144A1984A09D6A8D6930",
        filename="XUL.sym",
    )

    base_url = settings.SYMBOL_URLS[0]

    assert check_url_head(f"{base_url}{good_key}")
    assert not check_url_head(f"{base_url}{bad_key}")


def test_has_symbol(s3_helper):
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        data=b"abc123",
    )
    urls = ("http://localstack:4566/publicbucket/",)
    downloader = SymbolDownloader(urls, file_prefix="v1")
    assert downloader.has_symbol(
        "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
    )
    assert not downloader.has_symbol(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )


def test_get_url_public(s3_helper):
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        data=b"abc123",
    )
    urls = ("http://localstack:4566/publicbucket/",)
    downloader = SymbolDownloader(urls)
    url = downloader.get_symbol_url(
        "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
    )
    assert url == (
        "http://localstack:4566/publicbucket/v1/xul.pdb/"
        + "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
    )
    url = downloader.get_symbol_url(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )
    assert url is None


def test_public_default_file_prefix():
    """The idea with settings.SYMBOL_FILE_PREFIX is to make it easier
    to specify the settings.SYMBOL_URLS. That settings.SYMBOL_FILE_PREFIX
    is *always* used when uploading symbols. So it's *always* useful to
    query for symbols with a prefix. However, it's an easy mistake to make
    that you just focus on the bucket name to say where symbols come from.
    In those cases, the code should "protect" you can make sure we actually
    use the prefix.

    However, we don't want to lose the flexibility to actually override
    it on a *per URL* basis.
    """

    urls = (
        "http://localstack:4566/publicbucket/start/",
        # No trailing / in the path part
        "http://localstack:4566/publicbucket/prrffxx",
        # No prefix!
        "http://localstack:4566/publicbucket",
    )
    downloader = SymbolDownloader(urls, file_prefix="myprfx")
    assert not downloader.has_symbol(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )


def test_has_public_case_insensitive_debugid(s3_helper):
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        data=b"abc123",
    )
    urls = ("http://localstack:4566/publicbucket/",)
    downloader = SymbolDownloader(urls)
    assert downloader.has_symbol(
        "xul.pdb", "44e4ec8c2f41492b9369d6b9a059577c2", "xul.sym"
    )
