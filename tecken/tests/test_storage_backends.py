# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from datetime import datetime

import pytest
import requests

from tecken.ext.gcs.storage import GCSStorage
from tecken.ext.s3.storage import S3Storage
from tecken.libstorage import NoMatchingBackend, StorageBackend, StorageError
from tecken.tests.utils import Upload, UPLOADS


@pytest.mark.parametrize("upload", UPLOADS.values(), ids=UPLOADS.keys())
@pytest.mark.parametrize("storage_kind", ["gcs", "s3"])
def test_upload_and_download(get_test_storage_url, storage_kind: str, upload: Upload):
    url = get_test_storage_url(storage_kind)
    backend = StorageBackend.new(url)
    backend.clear()
    assert backend.exists()

    upload.upload_to_backend(backend)
    metadata = backend.get_object_metadata(upload.key)
    response = requests.get(metadata.download_url)
    response.raise_for_status()
    assert response.content == (upload.original_body or upload.body)
    assert isinstance(metadata.last_modified, datetime)
    assert metadata.content_length == upload.metadata.content_length
    assert metadata.content_encoding == upload.metadata.content_encoding
    assert (
        upload.metadata.content_type is None
        or metadata.content_type == upload.metadata.content_type
    )
    assert metadata.original_content_length == upload.metadata.original_content_length
    assert metadata.original_md5_sum == upload.metadata.original_md5_sum


@pytest.mark.parametrize("storage_kind", ["gcs", "s3"])
def test_non_exsiting_bucket(get_test_storage_url, storage_kind: str):
    url = get_test_storage_url(storage_kind)
    backend = StorageBackend.new(url)
    assert not backend.exists()


def test_unknown_hostname():
    with pytest.raises(NoMatchingBackend):
        StorageBackend.new("https://mozilla.org/test-bucket")


@pytest.mark.parametrize(
    "url,kind,name,prefix",
    [
        ("https://s3.amazonaws.com/some-bucket", "s3", "some-bucket", "v1"),
        ("https://s3-eu-west-2.amazonaws.com/other-bucket", "s3", "other-bucket", "v1"),
        ("http://s3.example.com/buck/prfx", "s3", "buck", "prfx/v1"),
        ("http://localstack:4566/publicbucket/try", "s3", "publicbucket", "try/v1"),
        ("https://storage.googleapis.com/some-bucket", "gcs", "some-bucket", "v1"),
        ("http://gcs.example.com/buck/prfx", "gcs", "buck", "prfx/v1"),
        ("http://gcs-emulator:8001/publicbucket/try", "gcs", "publicbucket", "try/v1"),
    ],
)
def test_storage_backend_new(url, kind, name, prefix):
    backend = StorageBackend.new(url)
    assert backend.name == name
    assert backend.prefix == prefix
    match kind:
        case "gcs":
            assert isinstance(backend, GCSStorage)
        case "s3":
            assert isinstance(backend, S3Storage)


@pytest.mark.parametrize("storage_kind", ["gcs", "s3"])
def test_storageerror_msg(get_test_storage_url, storage_kind: str):
    url = get_test_storage_url(storage_kind)
    backend = StorageBackend.new(url)
    error = StorageError(backend)
    assert repr(backend) in str(error)
