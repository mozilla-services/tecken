# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
import gzip
from hashlib import md5
from io import BytesIO
import os
from typing import Optional

import requests

from tecken.base.symbolstorage import SymbolStorage
from tecken.libstorage import ObjectMetadata, StorageBackend
from tecken.libsym import extract_sym_header_data


def _load_sym_file(path: str):
    path = os.path.join(os.path.dirname(__file__), "data", path)
    with open(path, "rb") as fp:
        body = fp.read()

    data = extract_sym_header_data(path)
    data["body"] = body
    return data


@dataclass
class Upload:
    debug_file: str
    debug_id: str
    sym_file: str
    body: bytes
    metadata: ObjectMetadata
    original_body: Optional[bytes] = None
    backend: Optional[StorageBackend] = None

    @property
    def key(self) -> str:
        return f"{self.debug_file}/{self.debug_id}/{self.sym_file}"

    @classmethod
    def uncompressed(cls, sym_file: str) -> "Upload":
        data = _load_sym_file(sym_file)

        metadata = ObjectMetadata(content_length=len(data["body"]))
        return cls(
            debug_file=data.get("debug_filename", ""),
            debug_id=data.get("debug_id", "").upper(),
            sym_file=sym_file,
            body=data["body"],
            metadata=metadata,
        )

    @classmethod
    def compressed(cls, sym_file: str) -> "Upload":
        data = _load_sym_file(sym_file)
        compressed_body = gzip.compress(data["body"])
        metadata = ObjectMetadata(
            content_type="text/plain",
            content_length=len(compressed_body),
            content_encoding="gzip",
            original_content_length=len(data["body"]),
            original_md5_sum=md5(data["body"]).hexdigest(),
        )
        return cls(
            debug_file=data.get("debug_filename", ""),
            debug_id=data.get("debug_id", "").upper(),
            sym_file=sym_file,
            body=compressed_body,
            metadata=metadata,
            original_body=data["body"],
        )

    def upload_to_backend(self, backend: StorageBackend):
        self.backend = backend
        backend.upload(self.key, BytesIO(self.body), self.metadata)

    def upload_to_backend_with_session(self, backend: StorageBackend):
        self.backend = backend
        url = backend.initiate_upload(self.key, self.metadata)
        self.upload_to_session_url(url)

    def upload_to_session_url(self, url: str):
        # NOTE(smarnach): GCS resumable uploads allow setting the Content-Type header either on
        # the request initiating the upload session or on the request uploading the data. We
        # include the Content-Type header in the request initiating the upload session, but the
        # emulator ignores it on that request, so the object ends up with a default content type
        # once the upload finishes. As a mitigation, we pass it again in the upload request.
        headers = {}
        if self.metadata.content_type:
            headers["Content-Type"] = self.metadata.content_type
        response = requests.put(url, self.body, headers=headers)
        response.raise_for_status()

    def upload(self, storage: SymbolStorage, try_storage: bool = False):
        backend = storage.get_upload_backend(try_storage)
        self.upload_to_backend(backend)


UPLOADS = {
    # Linux executable
    "uncompressed": Upload.uncompressed("teckentest_xpcshell.sym"),
    # Windows pdb file
    "compressed": Upload.compressed("teckentest_js.sym"),
    # macOS dylib file
    "special_chars": Upload.compressed("teckentest_libc++abi.dylib.sym"),
}
