# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
import gzip
from hashlib import md5
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests

from tecken.base.symbolstorage import SymbolStorage
from tecken.libstorage import ObjectMetadata, StorageBackend
from tecken.upload.views import FileSpecRequest


TEST_FILE_PATH = Path("./tecken/tests/data/symbols")


@dataclass
class Upload:
    debug_file: str
    debug_id: str
    sym_file: str
    body: bytes
    original_body: bytes
    metadata: ObjectMetadata
    backend: Optional[StorageBackend] = None

    @property
    def key(self) -> str:
        return f"{self.debug_file}/{self.debug_id}/{self.sym_file}"

    def md5_sum(self) -> str:
        return md5(self.original_body).hexdigest()

    def file_spec(self) -> FileSpecRequest:
        return FileSpecRequest(
            key=self.key, size=len(self.original_body), md5_hash=self.md5_sum()
        )

    @classmethod
    def from_test_file(cls, key: str) -> "Upload":
        with open(TEST_FILE_PATH / key, "rb") as f:
            body = f.read()
        original_body = body
        if key.endswith(".sym"):
            body = gzip.compress(body)
            metadata = ObjectMetadata(
                content_type="text/plain",
                content_length=len(body),
                content_encoding="gzip",
                original_content_length=len(original_body),
                original_md5_sum=md5(original_body).hexdigest(),
            )
        else:
            metadata = ObjectMetadata(content_length=len(body))
        debug_file, debug_id, sym_file = key.split("/")
        return cls(
            debug_file=debug_file,
            debug_id=debug_id,
            sym_file=sym_file,
            body=body,
            original_body=original_body,
            metadata=metadata,
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


TEST_FILE_KEYS = [
    # Windows executable with accompanying Breakpad symbols file
    "ShowSSEConfig.exe/6A4B9A365000/ShowSSEConfig.ex_",
    "ShowSSEConfig.exe/6A4B9A365000/ShowSSEConfig.sym",
    # Windows dynamic link library
    "libEGL.dll/6A4B8EEE10000/libEGL.dl_",
    # Windows program database with accompanying Breakpad symbols file
    "qipcap64.pdb/293A285ED25871934C4C44205044422E1/qipcap64.sym",
    "qipcap64.pdb/293A285ED25871934C4C44205044422E1/qipcap64.pd_",
    # Linux ELF binary with accompanying Breakpad symbols file
    "ssltunnel/8A07C88A3DA44E20A3490D88791183060/ssltunnel.dbg.gz",
    "ssltunnel/8A07C88A3DA44E20A3490D88791183060/ssltunnel.sym",
    # macOS debug symbols file with accompanying Breakpad symbols file
    "libxul_correct_buildid.dylib/BE555D35C9A93D7FBC23ED48502277E30/libxul_correct_buildid.dylib.dSYM.tar.bz2",
    "libxul_correct_buildid.dylib/BE555D35C9A93D7FBC23ED48502277E30/libxul_correct_buildid.dylib.sym",
    # A file with special characters in the file name
    "c++filt/B2E65520F14FB5332E38A5A5189839AD0/c++filt.sym",
]
UPLOADS = {key: Upload.from_test_file(key) for key in TEST_FILE_KEYS}
