# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from io import BufferedReader
from typing import Optional


class StorageError(Exception):
    """A backend-specific client reported an error."""

    # FIXME(willkg): this is unhelpful and drops a lot of exception magic
    def __init__(self, backend, url, error):
        self.backend = backend
        self.url = url
        self.backend_msg = f"{type(error).__name__}: {error}"

    def __str__(self):
        return f"{self.backend} backend ({self.url}) raised {self.backend_msg}"


def build_storage_backend():
    pass


@dataclass
class ObjectMetadata:
    """Metadata for an object in a storage.

    For use in the StorageBackend interface.
    """

    content_type: str
    content_length: int
    content_encoding: Optional[str] = None
    original_content_length: Optional[int] = None
    original_md5_sum: Optional[int] = None
    last_modified_timestamp: Optional[int] = None


@dataclass
class ObjectRedirect:
    """Indicates that the app should return a redirect to the given location for the object.

    For use in the StorageBackend interface.
    """

    location: str


@dataclass
class ObjectStream:
    """Indicates that the app should directly stream the given file.

    For use in the StorageBackend interface.
    """

    file: BufferedReader


ObjectDownload = ObjectRedirect | ObjectStream


class StorageBackend:
    """Interface for storage backends."""

    def exists(self) -> bool:
        """Check that this storage exists.

        :returns: True if the storage exists and False if not

        :raises StorageError: an unexpected backend-specific error was raised
        """
        raise NotImplementedError("exists() must be implemented by the concrete class")

    def get_object_metadata(self, key: str) -> Optional[ObjectMetadata]:
        """Return object metadata for the object with the given key.

        :returns: And OjbectMetadata instance if the object exist, None otherwise.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        raise NotImplementedError(
            "get_object_metadta() must be implemented by the concrete class"
        )

    def download(self, key: str) -> Optional[ObjectDownload]:
        """Return how the object with the given key can be downloaded.

        :returns:
            * An ObjectRedirect instance if the app should redirect the client.
            * An ObjectStream instance if the app should serve the object directly.
            * None if the object does not exist in the storage backend.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        raise NotImplementedError(
            "download() must be implemented by the concrete class"
        )

    def upload(self, key: str, body: BufferedReader, metadata: ObjectMetadata):
        """Upload the object with the given key and body to the storage backend.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        raise NotImplementedError("upload() must be implemented by the concrete class")
