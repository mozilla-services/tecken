# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
from typing import Optional

from django.utils import timezone

from tecken.libmarkus import METRICS
from tecken.ext.s3.storage import S3Storage
from tecken.libstorage import ObjectMetadata


logger = logging.getLogger("tecken")


class SymbolStorage:
    """
    Class for the following S3 tasks:

    1. Do you have this particular symbol?
    2. Give me the presigned URL for this particular symbol.

    This class takes a list of URLs.

    """

    def __init__(
        self, upload_url: str, download_urls: list[str], try_url: Optional[str] = None
    ):
        self.upload_backend = S3Storage(upload_url)
        download_backends = [
            S3Storage(url) for url in download_urls if url != upload_url
        ]
        if try_url is None:
            self.try_backend = None
        else:
            self.try_backend = S3Storage(try_url, try_symbols=True)
        self.backends = [self.upload_backend, *download_backends]

    def __repr__(self):
        urls = [backend.url for backend in self.backends]
        return f"<{self.__class__.__name__} urls={urls}>"

    @staticmethod
    def make_key(symbol: str, debugid: str, filename: str) -> str:
        """Generates a symbol file key for the given identifiers.

        :arg prefix:
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
        if try_storage and self.try_backend:
            backends = [*self.backends, self.try_backend]
        else:
            backends = self.backends
        for backend in backends:
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
    """Return the global SymbolStorage instance for regular storage."""
    # This function exists to make it easier to patch the SymbolStorage singleton in tests.
    return SYMBOL_STORAGE
