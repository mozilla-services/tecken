# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pytest

from tecken.base.symbolstorage import (
    SymbolStorage,
)


@pytest.mark.parametrize(
    "symbol, debugid, filename, expected",
    [
        (
            "xul.pdb",
            "44E4EC8C2F41492B9369D6B9A059577C2",
            "xul.sym",
            "xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        ),
        (
            "libc++abi.dylib",
            "43940F08B65E38888CD3C52398EB1CA10",
            "libc++abi.dylib.sym",
            "libc++abi.dylib/43940F08B65E38888CD3C52398EB1CA10/libc++abi.dylib.sym",
        ),
    ],
)
def test_make_url_path(symbol, debugid, filename, expected):
    path = SymbolStorage.make_key(symbol=symbol, debugid=debugid, filename=filename)
    assert path == expected


def test_has_symbol(s3_helper):
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        data=b"abc123",
    )
    storage = SymbolStorage(
        upload_url="http://localstack:4566/publicbucket/", download_urls=[]
    )
    assert storage.get_metadata(
        "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
    )
    assert not storage.get_metadata(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )


def test_get_url_public(s3_helper):
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        data=b"abc123",
    )
    storage = SymbolStorage(
        upload_url="http://localstack:4566/publicbucket/", download_urls=[]
    )
    metadata = storage.get_metadata(
        "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
    )
    assert metadata.download_url == (
        "http://localstack:4566/publicbucket/v1/xul.pdb/"
        + "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
    )
    metadata = storage.get_metadata(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )
    assert metadata is None


def test_has_public_case_insensitive_debugid(s3_helper):
    s3_helper.create_bucket("publicbucket")
    s3_helper.upload_fileobj(
        bucket_name="publicbucket",
        key="v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        data=b"abc123",
    )
    storage = SymbolStorage(
        upload_url="http://localstack:4566/publicbucket/", download_urls=[]
    )
    assert storage.get_metadata(
        "xul.pdb", "44e4ec8c2f41492b9369d6b9a059577c2", "xul.sym"
    )
