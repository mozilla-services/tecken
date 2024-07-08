# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
import gzip
from hashlib import md5
from io import BytesIO
from typing import Optional

from tecken.libstorage import ObjectMetadata, StorageBackend


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

    def upload(self, backend: StorageBackend):
        backend.upload(self.key, BytesIO(self.body), self.metadata)
