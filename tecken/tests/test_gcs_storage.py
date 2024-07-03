# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from datetime import datetime
import gzip
from hashlib import md5
from io import BytesIO
from typing import Optional

import requests

from tecken.ext.gcs.storage import GCSStorage
from tecken.libstorage import ObjectMetadata


@dataclass
class UploadData:
    key: str
    body: bytes
    metadata: ObjectMetadata
    original_body: Optional[bytes] = None

    @classmethod
    def uncompressed(cls, key: str, body: bytes):
        metadata = ObjectMetadata(content_length=len(body))
        return cls(key=key, body=body, metadata=metadata)

    @classmethod
    def compressed(cls, key: str, body: bytes):
        compressed_body = gzip.compress(body)
        metadata = ObjectMetadata(
            content_type="text/plain",
            content_length=len(compressed_body),
            content_encoding="gzip",
            original_content_length=len(body),
            original_md5_sum=md5(body).hexdigest(),
        )
        return cls(key=key, body=compressed_body, metadata=metadata, original_body=body)


def test_upload_and_download():
    uploads = [
        UploadData.uncompressed(key="a/b/c", body=b"test"),
        UploadData.compressed(
            key="libc++abi.dylib/43940F08B65E38888CD3C52398EB1CA10/libc++abi.dylib.sym",
            body=b"symbols file contents",
        ),
    ]
    backend = GCSStorage("http://gcs-emulator:8001/publicbucket")
    assert backend.exists()
    for upload in uploads:
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
        assert (
            metadata.original_content_length == upload.metadata.original_content_length
        )
        assert metadata.original_md5_sum == upload.metadata.original_md5_sum
