# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from tecken.tests.utils import UPLOADS


def test_get_metadata(symbol_storage):
    upload = UPLOADS["compressed"]
    upload.upload(symbol_storage)
    debug_id = upload.debug_id
    metadata = symbol_storage.get_metadata(
        f"teckentest_js.pdb/{debug_id}/teckentest_js.sym"
    )
    assert metadata.download_url

    # NOTE(willkg): this requests a symbol file that doesn't exist in storage
    assert not symbol_storage.get_metadata(
        "xxx.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym"
    )
