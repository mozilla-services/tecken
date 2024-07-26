# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from io import BufferedReader
import threading
from typing import Optional
from urllib.parse import quote

import boto3.session
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from tecken.libstorage import ObjectMetadata, StorageBackend, StorageError


class S3Storage(StorageBackend):
    """
    An implementation of the StorageBackend interface for Amazon S3.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str,
        try_symbols: bool = False,
        endpoint_url: Optional[str] = None,
        region: Optional[str] = None,
    ):
        self.bucket = bucket
        self.prefix = prefix
        self.try_symbols = try_symbols
        self.endpoint_url = endpoint_url
        self.region = region
        self.clients = threading.local()

    def __repr__(self):
        return f"<{self.__class__.__name__} s3://{self.bucket}/{self.prefix} try:{self.try_symbols}>"

    def _get_client(self):
        """Return a backend-specific client."""
        if not hasattr(self.clients, "storage"):
            options = {
                "config": Config(
                    read_timeout=settings.S3_READ_TIMEOUT,
                    connect_timeout=settings.S3_CONNECT_TIMEOUT,
                )
            }
            if self.endpoint_url:
                options["endpoint_url"] = self.endpoint_url
            if self.region:
                options["region_name"] = self.region
            self.clients.storage = _get_boto3_session().client("s3", **options)
        return self.clients.storage

    def exists(self) -> bool:
        """Check that this storage exists.

        :returns: True if the storage exists and False if not

        :raises StorageError: an unexpected backend-specific error was raised
        """
        client = self._get_client()

        try:
            client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            # A generic ClientError can be raised if:
            # - The bucket doesn't exist (code 404)
            # - The user doesn't have s3:ListBucket perm (code 403)
            # - Other credential issues (code 403, maybe others)
            if exc.response["Error"]["Code"] == "404":
                return False
            else:
                raise StorageError(str(exc), backend=self) from exc
        except BotoCoreError as exc:
            raise StorageError(str(exc), backend=self) from exc
        else:
            return True

    def get_object_metadata(self, key: str) -> Optional[ObjectMetadata]:
        """Return object metadata for the object with the given key.

        :arg key: the key of the symbol file not including the prefix, i.e. the key in the format
            ``<debug-file>/<debug-id>/<symbols-file>``.

        :returns: An OjbectMetadata instance if the object exist, None otherwise.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        client = self._get_client()
        s3_key = f"{self.prefix}/{key}"
        try:
            response = client.head_object(Bucket=self.bucket, Key=s3_key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return None
            raise StorageError(str(exc), backend=self) from exc
        except BotoCoreError as exc:
            raise StorageError(str(exc), backend=self) from exc
        s3_metadata = response.get("Metadata", {})
        original_content_length = s3_metadata.get("original_size")
        if original_content_length is not None:
            try:
                original_content_length = int(original_content_length)
            except ValueError:
                original_content_length = None
        endpoint_url = client.meta.endpoint_url.removesuffix("/")
        metadata = ObjectMetadata(
            download_url=f"{endpoint_url}/{self.bucket}/{quote(s3_key)}",
            content_type=response.get("ContentType"),
            content_length=response["ContentLength"],
            content_encoding=response.get("ContentEncoding"),
            original_content_length=original_content_length,
            original_md5_sum=s3_metadata.get("original_md5_hash"),
            last_modified=response.get("LastModified"),
        )
        return metadata

    def upload(self, key: str, body: BufferedReader, metadata: ObjectMetadata):
        """Upload the object with the given key and body to the storage backend.

        :arg key: the key of the symbol file not including the prefix, i.e. the key in the format
            ``<debug-file>/<debug-id>/<symbols-file>``.
        :arg body: An stream yielding the symbols file contents.
        :arg metadata: An ObjectMetadata instance with the metadata.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        # boto3 performs strict type checking for all keyword parameters, and passing None where
        # it expects a string doesn't work, so we need to completely remove these parameters.
        s3_metadata = {}
        if metadata.original_content_length:
            # All metadata values must be strings.
            s3_metadata["original_size"] = str(metadata.original_content_length)
        if metadata.original_md5_sum:
            s3_metadata["original_md5_hash"] = metadata.original_md5_sum
        kwargs = {
            "Bucket": self.bucket,
            "Key": f"{self.prefix}/{key}",
            "Body": body,
            "Metadata": s3_metadata,
        }
        if metadata.content_type:
            kwargs["ContentType"] = metadata.content_type
        if metadata.content_encoding:
            kwargs["ContentEncoding"] = metadata.content_encoding
        if metadata.content_length:
            kwargs["ContentLength"] = metadata.content_length

        client = self._get_client()
        try:
            client.put_object(**kwargs)
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(str(exc), backend=self) from exc


_BOTO3_SESSION_CACHE = threading.local()


def _get_boto3_session() -> boto3.session.Session:
    """Return the boto3 session for the current thread."""
    if not hasattr(_BOTO3_SESSION_CACHE, "session"):
        _BOTO3_SESSION_CACHE.session = boto3.session.Session()
    return _BOTO3_SESSION_CACHE.session
