# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from datetime import datetime
from urllib.parse import urlparse

import pytest
import requests

from tecken.libstorage import StorageError
from tecken.tests.utils import Upload, UPLOADS


@pytest.mark.parametrize("use_upload_session", [False, True])
@pytest.mark.parametrize("try_storage", [False, True])
@pytest.mark.parametrize("upload", UPLOADS.values(), ids=UPLOADS.keys())
@pytest.mark.parametrize("storage_kind", ["gcs", "gcs-cdn"])
def test_upload_and_download(
    get_storage_backend,
    storage_kind: str,
    upload: Upload,
    try_storage: bool,
    use_upload_session: bool,
):
    backend = get_storage_backend(storage_kind, try_storage)
    backend.clear()
    assert backend.exists()

    if use_upload_session:
        upload.upload_to_backend_with_session(backend)
    else:
        upload.upload_to_backend(backend)
    metadata = backend.get_object_metadata(upload.key)
    response = requests.get(metadata.download_url)
    response.raise_for_status()
    assert response.content == (upload.original_body or upload.body)
    assert isinstance(metadata.last_modified, datetime)
    assert metadata.content_length == upload.metadata.content_length
    assert metadata.content_encoding == upload.metadata.content_encoding
    if metadata.content_encoding is None:
        assert metadata.original_content_length == upload.metadata.content_length
        assert metadata.original_md5_sum == upload.md5_sum()
    else:
        assert metadata.content_type == upload.metadata.content_type
        assert (
            metadata.original_content_length == upload.metadata.original_content_length
        )
        assert metadata.original_md5_sum == upload.metadata.original_md5_sum


@pytest.mark.parametrize("storage_kind", ["gcs", "gcs-cdn"])
def test_non_exsiting_bucket(get_storage_backend, storage_kind: str):
    backend = get_storage_backend(storage_kind)
    assert not backend.exists()


@pytest.mark.parametrize("storage_kind", ["gcs", "gcs-cdn"])
def test_storageerror_msg(get_storage_backend, storage_kind: str):
    backend = get_storage_backend(storage_kind)
    error = StorageError("storage error message", backend=backend)
    assert repr(backend) in str(error)


@pytest.mark.parametrize("storage_kind", ["gcs", "gcs-cdn"])
def test_download_url(bucket_name: str, get_storage_backend, storage_kind: str):
    backend = get_storage_backend(storage_kind)
    backend.clear()
    upload = UPLOADS["c++filt/B2E65520F14FB5332E38A5A5189839AD0/c++filt.sym"]
    upload.upload_to_backend(backend)
    metadata = backend.get_object_metadata(upload.key)
    parsed_url = urlparse(metadata.download_url)
    bucket, _, key = parsed_url.path[1:].partition("/")
    assert bucket == bucket_name
    assert key == "v1/c%2B%2Bfilt/B2E65520F14FB5332E38A5A5189839AD0/c%2B%2Bfilt.sym"
