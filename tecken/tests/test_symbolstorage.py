# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pytest

from tecken.base.symbolstorage import SymbolStorage
from tecken.tests.utils import UPLOADS


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
    upload = UPLOADS["compressed"]
    upload.upload(symbol_storage)
    debug_id = upload.debug_id
    if lower_case_debug_id:
        debug_id = debug_id.lower()
    metadata = symbol_storage.get_metadata("xul.pdb", debug_id, "xul.sym")
    assert metadata.download_url
    assert not symbol_storage.get_metadata(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )
