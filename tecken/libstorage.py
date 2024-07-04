# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
import datetime
from io import BufferedReader
from typing import Optional
from urllib.parse import urlparse


@dataclass
class ObjectMetadata:
    """Metadata for an object in a storage.

    For use in the StorageBackend interface.
    """

    content_type: Optional[str] = None
    content_length: Optional[int] = None
    content_encoding: Optional[str] = None
    original_content_length: Optional[int] = None
    original_md5_sum: Optional[str] = None
    last_modified: Optional[datetime.datetime] = None
    download_url: Optional[str] = None


class StorageBackend:
    """Interface for storage backends."""

    # The bucket name for this backend
    name: str

    # Configured backend URL
    url: str

    # Whether the backend handles try symboles
    try_symbols: bool

    # Class attribute that lists the accepted hostnames.
    accepted_hostnames: tuple[str, ...]

    def __init_subclass__(cls):
        assert hasattr(cls, "accepted_hostnames")
        _BACKEND_CLASSES.append(cls)

    @classmethod
    def new(cls, url: str, try_symbols: bool = False) -> "StorageBackend":
        """Create an instance of a StorageBackend subclass.

        The hostname part of the given URL is checked against the ``acepted_hostnames`` list of all
        implementations of ``StorageBackend``. If the URL hostname ends with any of the accepted
        hostnames, the corresponding class is instantiated.

        :returns: A new instance of a StorageBackend subclass.

        :raises: NoMatchingBackend id no subclass accepts the URL.
        """
        # The modules in the ext package are not explicitly imported anywhere. We need to make sure
        # _BACKEND_CLASSES is fully populated before proceeding. The redundant alias pacifies ruff.
        from tecken import ext as ext

        hostname = urlparse(url).hostname.lower().removesuffix(".")
        for backend_class in _BACKEND_CLASSES:
            if hostname.endswith(backend_class.accepted_hostnames):
                return backend_class(url, try_symbols)
        raise NoMatchingBackend(url)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} name={self.name} url={self.url} "
            + f"try_symbols={self.try_symbols}"
        )

    def exists(self) -> bool:
        """Check that this storage exists.

        :returns: True if the storage exists and False if not

        :raises StorageError: an unexpected backend-specific error was raised
        """
        raise NotImplementedError("exists() must be implemented by the concrete class")

    def get_object_metadata(self, key: str) -> Optional[ObjectMetadata]:
        """Return object metadata for the object with the given key.

        :arg key: the key of the symbol file not including the prefix, i.e. the key in the format
            ``<debug-file>/<debug-id>/<symbols-file>``.

        :returns: An OjbectMetadata instance if the object exist, None otherwise.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        raise NotImplementedError(
            "get_object_metadata() must be implemented by the concrete class"
        )

    def upload(self, key: str, body: BufferedReader, metadata: ObjectMetadata):
        """Upload the object with the given key and body to the storage backend.

        :arg key: the key of the symbol file not including the prefix, i.e. the key in the format
            ``<debug-file>/<debug-id>/<symbols-file>``.
        :arg body: A stream yielding the symbols file contents.
        :arg metadata: An ObjectMetadata instance with the metadata.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        raise NotImplementedError("upload() must be implemented by the concrete class")


class StorageError(Exception):
    """A backend-specific client reported an error."""

    def __init__(self, backend: StorageBackend):
        super().__init__(f"Error in backend {backend!r}")


class NoMatchingBackend(Exception):
    """No backend class accepts the given URL."""

    def __init__(self, url: str):
        super().__init__(f"No backend class accepts URL {url}")


# List of all classes implementing StorageBackend
_BACKEND_CLASSES: list[type[StorageBackend]] = []
