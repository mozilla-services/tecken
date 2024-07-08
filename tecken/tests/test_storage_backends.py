# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from datetime import datetime
import gzip
from hashlib import md5
from io import BytesIO
from typing import Optional

import pytest
import requests

from tecken.ext.gcs.storage import GCSStorage
from tecken.ext.s3.storage import S3Storage
from tecken.libstorage import (
    NoMatchingBackend,
    ObjectMetadata,
    StorageBackend,
    StorageError,
)


@dataclass
class Upload:
    key: str
    body: bytes
    metadata: ObjectMetadata
    original_body: Optional[bytes] = None

    @classmethod
    def uncompressed(cls, key: str, body: bytes) -> "Upload":
        metadata = ObjectMetadata(content_length=len(body))
        return cls(key=key, body=body, metadata=metadata)

    @classmethod
    def compressed(cls, key: str, body: bytes) -> "Upload":
        compressed_body = gzip.compress(body)
        metadata = ObjectMetadata(
            content_type="text/plain",
            content_length=len(compressed_body),
            content_encoding="gzip",
            original_content_length=len(body),
            original_md5_sum=md5(body).hexdigest(),
        )
        return cls(key=key, body=compressed_body, metadata=metadata, original_body=body)


UPLOADS = [
    Upload.uncompressed(key="a/b/c", body=b"test"),
    Upload.compressed(
        key="libc++abi.dylib/43940F08B65E38888CD3C52398EB1CA10/libc++abi.dylib.sym",
        body=b"symbols file contents",
    ),
]


@pytest.mark.parametrize("upload", UPLOADS)
@pytest.mark.parametrize("storage_kind", ["gcs", "s3"])
def test_upload_and_download(create_storage_backend, storage_kind: str, upload: Upload):
    backend: StorageBackend = create_storage_backend(storage_kind)
    assert backend.exists()
    backend.upload(upload.key, BytesIO(upload.body), upload.metadata)
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
