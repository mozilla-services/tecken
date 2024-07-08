# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
import gzip
from hashlib import md5
from io import BytesIO
from typing import Optional

from tecken.base.symbolstorage import SymbolStorage
from tecken.libstorage import ObjectMetadata, StorageBackend


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
    def key(self):
        return SymbolStorage.make_key(self.debug_file, self.debug_id, self.sym_file)

    @classmethod
    def uncompressed(
        cls, debug_file: str, debug_id: str, sym_file: str, body: bytes
    ) -> "Upload":
        metadata = ObjectMetadata(content_length=len(body))
        return cls(
            debug_file=debug_file,
            debug_id=debug_id,
            sym_file=sym_file,
            body=body,
            metadata=metadata,
        )

    @classmethod
    def compressed(
        cls, debug_file: str, debug_id: str, sym_file: str, body: bytes
    ) -> "Upload":
        compressed_body = gzip.compress(body)
        metadata = ObjectMetadata(
            content_type="text/plain",
            content_length=len(compressed_body),
            content_encoding="gzip",
            original_content_length=len(body),
            original_md5_sum=md5(body).hexdigest(),
        )
        return cls(
            debug_file=debug_file,
            debug_id=debug_id,
            sym_file=sym_file,
            body=compressed_body,
            metadata=metadata,
            original_body=body,
        )

    def upload_to_backend(self, backend: StorageBackend):
        self.backend = backend
        backend.upload(self.key, BytesIO(self.body), self.metadata)

    def upload(self, storage: SymbolStorage, try_storage: bool = False):
        backend = storage.get_upload_backend(try_storage)
        self.upload_to_backend(backend)


UPLOADS = {
    "uncompressed": Upload.uncompressed(
        debug_file="a", debug_id="b", sym_file="c", body=b"test"
    ),
    "compressed": Upload.compressed(
        debug_file="xul.pdb",
        debug_id="44E4EC8C2F41492B9369D6B9A059577C2",
        sym_file="xul.sym",
        body=b"symbols file contents",
    ),
    "special_chars": Upload.compressed(
        debug_file="libc++abi.dylib",
        debug_id="43940F08B65E38888CD3C52398EB1CA10",
        sym_file="libc++abi.dylib.sym",
        body=b"symbols file contents",
    ),
}
