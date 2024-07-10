# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from io import BufferedReader
import threading
from typing import Optional
from urllib.parse import quote

from django.conf import settings

from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import ClientError, NotFound
from google.cloud import storage

from tecken.libstorage import ObjectMetadata, StorageBackend, StorageError


class GCSStorage(StorageBackend):
    """
    An implementation of the StorageBackend interface for Google Cloud Storage.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str,
        try_symbols: bool = False,
        endpoint_url: Optional[str] = None,
        public_url: Optional[str] = None,
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.try_symbols = try_symbols
        self.endpoint_url = endpoint_url
        if public_url:
            self.public_url = public_url.removesuffix("/")
        else:
            self.public_url = None
        self.clients = threading.local()
        # The Cloud Storage client doesn't support setting global timeouts for all requests, so we
        # need to pass the timeout for every single request. the default timeout is 60 seconds for
        # both connecting and reading from the socket.
        self.timeout = (settings.STORAGE_CONNECT_TIMEOUT, settings.STORAGE_READ_TIMEOUT)

    def __repr__(self):
        return f"<{self.__class__.__name__} gs://{self.bucket}/{self.prefix}> try:{self.try_symbols}"

    def _get_client(self) -> storage.Client:
        """Return a thread-local low-level storage client."""
        if not hasattr(self.clients, "client"):
            options = ClientOptions(api_endpoint=self.endpoint_url)
            self.clients.client = storage.Client(client_options=options)
        return self.clients.client

    def _get_bucket(self) -> storage.Bucket:
        """Return a thread-local low-level storage bucket client."""
        if not hasattr(self.clients, "bucket"):
            client = self._get_client()
            try:
                self.clients.bucket = client.get_bucket(
                    self.bucket, timeout=self.timeout
                )
            except NotFound as exc:
                raise StorageError(str(exc), backend=self) from exc
        return self.clients.bucket

    def exists(self) -> bool:
        """Check that this storage exists.

        :returns: True if the storage exists and False if not

        :raises StorageError: an unexpected backend-specific error was raised
        """
        try:
            self._get_bucket()
        except StorageError:
            return False
        except ClientError as exc:
            raise StorageError(str(exc), backend=self) from exc
        return True

    def get_download_url(self, key: str) -> str:
        """Return the download URL for the given key."""
        endpoint_url = self.endpoint_url or self._get_client().meta.endpoint_url
        endpoint_url = endpoint_url.removesuffix("/")
        return f"{endpoint_url}/{self.bucket}/{self.prefix}/{quote(key)}"

    def get_object_metadata(self, key: str) -> Optional[ObjectMetadata]:
        """Return object metadata for the object with the given key.

        :arg key: the key of the symbol file not including the prefix, i.e. the key in the format
            ``<debug-file>/<debug-id>/<symbols-file>``.

        :returns: An OjbectMetadata instance if the object exist, None otherwise.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        bucket = self._get_bucket()
        gcs_key = f"{self.prefix}/{key}"
        try:
            blob = bucket.get_blob(gcs_key, timeout=self.timeout)
            if not blob:
                return None
        except ClientError as exc:
            raise StorageError(str(exc), backend=self) from exc
        gcs_metadata = blob.metadata or {}
        original_content_length = gcs_metadata.get("original_size")
        if original_content_length is not None:
            try:
                original_content_length = int(original_content_length)
            except ValueError:
                original_content_length = None
        if self.public_url:
            download_url = f"{self.public_url}/{quote(gcs_key)}"
        else:
            download_url = blob.public_url
        metadata = ObjectMetadata(
            download_url=download_url,
            content_type=blob.content_type,
            content_length=blob.size,
            content_encoding=blob.content_encoding,
            original_content_length=original_content_length,
            original_md5_sum=gcs_metadata.get("original_md5_hash"),
            last_modified=blob.updated,
        )
        return metadata

    def upload(self, key: str, body: BufferedReader, metadata: ObjectMetadata):
        """Upload the object with the given key and body to the storage backend.

        :arg key: the key of the symbol file not including the prefix, i.e. the key in the format
            ``<debug-file>/<debug-id>/<symbols-file>``.
        :arg body: A stream yielding the symbols file contents.
        :arg metadata: An ObjectMetadata instance with the metadata.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        bucket = self._get_bucket()
        blob = bucket.blob(f"{self.prefix}/{key}")
        gcs_metadata = {}
        if metadata.original_content_length:
            # All metadata values must be strings.
            gcs_metadata["original_size"] = str(metadata.original_content_length)
        if metadata.original_md5_sum:
            gcs_metadata["original_md5_hash"] = metadata.original_md5_sum
        blob.metadata = gcs_metadata
        blob.content_type = metadata.content_type
        blob.content_encoding = metadata.content_encoding
        # Prevent "decompressive transcoding" on download. See bug 1827506.
        blob.cache_control = "no-transform"
        try:
            blob.upload_from_file(
                body, size=metadata.content_length, timeout=self.timeout
            )
        except ClientError as exc:
            raise StorageError(str(exc), backend=self) from exc
