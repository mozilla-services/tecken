# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from collections.abc import Callable
from dataclasses import dataclass
import datetime
from io import BufferedReader
from threading import Event
from typing import Any, ClassVar, Literal, Optional

from django.utils.module_loading import import_string


@dataclass
class ObjectMetadata:
    """Metadata for an object in a storage.

    For use in the StorageBackend and NotificationQueue interfaces.
    """

    content_type: Optional[str] = None
    content_length: Optional[int] = None
    content_encoding: Optional[str] = None
    original_content_length: Optional[int] = None
    original_md5_sum: Optional[str] = None
    last_modified: Optional[datetime.datetime] = None
    download_url: Optional[str] = None
    upload_id: Optional[int] = None


class StorageBackend:
    """Interface for storage backends."""

    # The bucket name for this backend
    bucket: str

    # The prefix for object keys in the bucket
    prefix: str

    # Whether the backend handles try symboles
    try_symbols: bool

    # The name of the protocol for upload sessions started with initiate_upload. This name is
    # passed on to clients together with the upload session URL, and each protocol name should
    # be documented in the service documentation.
    upload_session_protocol: ClassVar[str]

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

    def initiate_upload(self, key: str, metadata: ObjectMetadata) -> str:
        """Initiate uploading an object with the given key to the storage backend.

        This function starts an upload session for the given key, and returns a URL that can be
        used to upload the object data using the protocol named in the upload_session_protocol
        class variable.

        :arg key: the key of the symbol file not including the prefix, i.e. the key in the format
            ``<debug-file>/<debug-id>/<symbols-file>``.
        :arg metadata: An ObjectMetadata instance with the metadata.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        raise NotImplementedError(
            "initiate_upload() must be implemented by the concrete class"
        )


class StorageError(Exception):
    """A backend-specific client reported an error."""

    def __init__(self, msg: str, backend: StorageBackend):
        super().__init__(f"Error: backend {backend!r}: {msg}")


def backend_from_config(config: dict[str, Any]) -> StorageBackend:
    cls = import_string(config["class"])
    return cls(**config["options"])


@dataclass
class Notification:
    """Notification data for a storage object event."""

    # The type of the storage event. Currently supported values:
    #     finalize_new: a new file was fully uploaded.
    #     finalize_update: an file overwriting an existing object was fully uploaded.
    event_type: Literal["finalize_new", "finalize_update"]

    # The timestamp of the event
    event_time: datetime.datetime

    # The lookup key of the uploaded symbols file, i.e. <debug_file>/<debug_id>/<sym_file>.
    key: str

    # The metadata for the object.
    metadata: ObjectMetadata


class NotificationQueue:
    """Interface for processing storage object notifications."""

    def subscribe(
        self,
        process: Callable[[Notification], None],
        stop_event: Event | None = None,
    ):
        """Subscribe to storage object notifications.

        This function calls the provided function for each received notification. If the callback
        finishes without error, the message is automatically acknowledged.

        :arg process: a function taking and processing a Notification instance.
        :arg stop_event: an optional event used to stop the subscription gracefully.
        """
        raise NotImplementedError(
            "subscribe() must be implemented by the concrete class"
        )


def queue_from_config(config: dict[str, Any]) -> NotificationQueue:
    cls = import_string(config["class"])
    return cls(**config["options"])
