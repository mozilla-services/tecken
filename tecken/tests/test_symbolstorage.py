# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pytest

from tecken.base.symbolstorage import SymbolStorage
from tecken.tests.utils import Upload


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


@pytest.mark.parametrize("lower_case_debug_id", [False, True])
def test_get_metadata(symbol_storage, lower_case_debug_id):
    backend = symbol_storage.get_upload_backend(False)
    upload = Upload.uncompressed(
        key="xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym", body=b"abc123"
    )
    upload.upload(backend)
    debug_id = "44E4EC8C2F41492B9369D6B9A059577C2"
    if lower_case_debug_id:
        debug_id = debug_id.lower()
    metadata = symbol_storage.get_metadata("xul.pdb", debug_id, "xul.sym")
    assert metadata.download_url == (
        f"{backend.url}/v1/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
    )
    assert not symbol_storage.get_metadata(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )
