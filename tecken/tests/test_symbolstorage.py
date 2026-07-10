# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pytest

from tecken.tests.utils import UPLOADS


@pytest.mark.parametrize(("key", "upload"), UPLOADS.items())
def test_get_metadata(symbol_storage, key, upload):
    upload.upload(symbol_storage)
    metadata = symbol_storage.get_metadata(key)
    assert metadata.download_url
    assert metadata.content_length == len(upload.body)
    assert metadata.content_encoding == upload.metadata.content_encoding
    assert metadata.content_type == (
        upload.metadata.content_type or "application/octet-stream"
    )


def test_get_metadata_non_existing(symbol_storage):
    # NOTE(willkg): this requests a symbol file that doesn't exist in storage
    assert not symbol_storage.get_metadata(
        "xxx.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym"
    )
