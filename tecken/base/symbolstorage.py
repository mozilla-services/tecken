# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
from typing import Optional

from django.conf import settings
from django.utils import timezone

from tecken.libmarkus import METRICS
from tecken.libstorage import ObjectMetadata, StorageBackend


logger = logging.getLogger("tecken")


class SymbolStorage:
    """Persistent wrapper around multiple StorageBackend instances."""

    def __init__(
        self, upload_url: str, download_urls: list[str], try_url: Optional[str] = None
    ):
        # The upload backend for regular storage.
        self.upload_backend: StorageBackend = StorageBackend.new(upload_url)

        # All additional download backends, except for the regular upload backend.
        download_backends = [
            StorageBackend.new(url) for url in download_urls if url != upload_url
        ]

        # All backends
        self.backends: list[StorageBackend] = [self.upload_backend, *download_backends]

        # The try storage backend for both upload and download, if any.
        if try_url is None:
            self.try_backend: Optional[StorageBackend] = None
        else:
            self.try_backend: Optional[StorageBackend] = StorageBackend.new(
                try_url, try_symbols=True
            )
            self.backends.append(self.try_backend)

    @classmethod
    def from_settings(cls):
        return cls(
            upload_url=settings.UPLOAD_DEFAULT_URL,
            download_urls=settings.SYMBOL_URLS,
            try_url=settings.UPLOAD_TRY_SYMBOLS_URL,
        )

    def __repr__(self):
        urls = [backend.url for backend in self.backends]
        return f"<{self.__class__.__name__} urls={urls}>"

    def get_download_backends(self, try_storage: bool) -> list[StorageBackend]:
        """Return a list of all download backends.

        Includes the try backend if `try_storage` is set to `True`.
        """
        return [
            backend
            for backend in self.backends
            if try_storage or not backend.try_symbols
        ]

    def get_upload_backend(self, try_storage: bool) -> StorageBackend:
        """Return either the regular or the try upload backends."""
        if try_storage:
            return self.try_backend
        return self.upload_backend

    @staticmethod
    def make_key(symbol: str, debugid: str, filename: str) -> str:
        """Generates a symbol file key for the given identifiers.

        :arg symbol:
        :arg debugid:
        :arg filename:

        :returns: A key suitable for use with StorageBackend methods.
        """
        # There are some legacy use case where the debug ID might not already be
        # uppercased. If so, we override it. Every debug ID is always in uppercase.
        return f"{symbol}/{debugid.upper()}/{filename}"

    def get_metadata(
        self, symbol: str, debugid: str, filename: str, try_storage: bool = False
    ) -> Optional[ObjectMetadata]:
        """Return the metadata of the symbols file if it can be found, and None otherwise."""
        key = self.make_key(symbol=symbol, debugid=debugid, filename=filename)
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
