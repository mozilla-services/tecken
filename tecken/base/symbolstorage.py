# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
from typing import Optional

from django.conf import settings
from django.utils import timezone

from tecken.libmarkus import METRICS
from tecken.libstorage import ObjectMetadata, StorageBackend, backend_from_config


logger = logging.getLogger("tecken")


class SymbolStorage:
    """Persistent wrapper around multiple StorageBackend instances.

    :arg upload_backend: The upload and download backend for regular storage.
    :arg try_upload_backend: The upload and download backend for try storage.
    :arg download_backends: Additional download backends.
    """

    def __init__(
        self,
        upload_backend: StorageBackend,
        try_upload_backend: StorageBackend,
        download_backends: list[StorageBackend],
    ):
        self.upload_backend = upload_backend
        self.try_upload_backend = try_upload_backend
        self.backends = [upload_backend, try_upload_backend, *download_backends]

    @classmethod
    def from_settings(cls):
        upload_backend = backend_from_config(settings.UPLOAD_BACKEND)
        try_upload_backend = backend_from_config(settings.TRY_UPLOAD_BACKEND)
        download_backends = list(map(backend_from_config, settings.DOWNLOAD_BACKENDS))
        return cls(upload_backend, try_upload_backend, download_backends)

    def __repr__(self):
        backend_reprs = " ".join(map(repr, self.backends))
        return f"<{self.__class__.__name__} backends: {backend_reprs}>"

    def get_download_backends(self, try_storage: bool) -> list[StorageBackend]:
        """Return a list of all download backends.

        Includes the try backend if `try_storage` is set to `True`.
        """
        if try_storage:
            return self.backends
        return [backend for backend in self.backends if not backend.try_symbols]

    def get_upload_backend(self, try_storage: bool) -> StorageBackend:
        """Return either the regular or the try upload backends."""
        if try_storage:
            return self.try_upload_backend
        return self.upload_backend

    def get_metadata(
        self, key: str, try_storage: bool = False
    ) -> Optional[ObjectMetadata]:
        """Return the metadata of the symbols file if it can be found, and None otherwise."""
        for backend in self.get_download_backends(try_storage):
            with METRICS.timer("symboldownloader_exists"):
                metadata = backend.get_object_metadata(key)
            if metadata:
                if metadata.last_modified:
                    age_days = (timezone.now() - metadata.last_modified).days
                    if backend.try_symbols:
                        tags = ["storage:try"]
                    else:
                        tags = ["storage:regular"]
                    METRICS.histogram("symboldownloader.file_age_days", age_days, tags)
                return metadata


# Global SymbolStorage instance, eventually used for all interactions with storage backends.
SYMBOL_STORAGE: Optional[SymbolStorage] = None


def symbol_storage() -> Optional[SymbolStorage]:
    """Return the global SymbolStorage instance."""
    # This function exists to make it easier to patch the SymbolStorage singleton in tests.
    return SYMBOL_STORAGE
