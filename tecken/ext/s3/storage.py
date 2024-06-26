# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from io import BufferedReader
import re
import threading
from typing import Optional
from urllib.parse import quote, urlparse

import boto3.session
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from django.conf import settings

from tecken.libstorage import ObjectMetadata, StorageBackend, StorageError


ALL_POSSIBLE_S3_REGIONS: tuple[str] = tuple(
    boto3.session.Session().get_available_regions("s3")
)


class S3Storage(StorageBackend):
    """
    Deconstructs a URL about an S3 bucket and breaks it into parts that
    can be used for various purposes. Also, contains a convenient method
    for getting a boto3 s3 client instance ultimately based on the URL.

    Usage::

        >>> s = S3Storage(
        ...    'https://s3-us-west-2.amazonaws.com/bucky/prfx'
        )
        >>> s.netloc
        's3-us-west-2.amazonaws.com'
        >>> s.name
        'bucky'
        >>> s.prefix
        'prfx'
        >>> s.client.list_objects_v2(Bucket=s.name, Prefix='some/key.ext')

    """

    # A substring match of the domain is used to recognize storage backends.
    # For emulated backends, the name should be present in the docker compose
    # service name.
    _URL_FINGERPRINT: list[str] = {
        # AWS S3, like bucket-name.s3.amazonaws.com
        "s3": ".amazonaws.com",
        # Localstack S3 Emulator
        "emulated-s3": "localstack",
        # S3 test domain
        "test-s3": "s3.example.com",
    }

    def __init__(
        self,
        url: str,
        try_symbols: bool = False,
        file_prefix: str = settings.SYMBOL_FILE_PREFIX,
    ):
        self.url = url
        parsed = urlparse(url)
        self.scheme = parsed.scheme
        self.netloc = parsed.netloc

        # Determine the backend from the netloc (domain plus port)
        self.backend = None
        for backend, fingerprint in self._URL_FINGERPRINT.items():
            if fingerprint in self.netloc:
                self.backend = backend
                break
        if self.backend is None:
            raise ValueError(f"Storage backend not recognized in {url!r}")

        try:
            name, prefix = parsed.path[1:].split("/", 1)
            if prefix.endswith("/"):
                prefix = prefix[:-1]
        except ValueError:
            prefix = ""
            name = parsed.path[1:]
        self.name = name
        if file_prefix:
            if prefix:
                prefix += f"/{file_prefix}"
            else:
                prefix = file_prefix
        self.prefix = prefix
        self.try_symbols = try_symbols
        self.endpoint_url = None
        self.region = None
        if not self.backend == "s3":
            # the endpoint_url will be all but the path
            self.endpoint_url = f"{parsed.scheme}://{parsed.netloc}"
        region = re.findall(r"s3-(.*)\.amazonaws\.com", parsed.netloc)
        if region:
            if region[0] not in ALL_POSSIBLE_S3_REGIONS:
                raise ValueError(f"Not valid S3 region {region[0]}")
            self.region = region[0]
        self.clients = threading.local()

    @property
    def base_url(self):
        """Return the URL by its domain and bucket name"""
        return f"{self.scheme}://{self.netloc}/{self.name}"

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} name={self.name!r} "
            + f"endpoint_url={self.endpoint_url!r} region={self.region!r} "
            + f"backend={self.backend!r}>"
        )

    def get_storage_client(self):
        """Return a backend-specific client.

        TODO(jwhitlock): Build up S3Storage API so users don't work directly with
        the backend-specific clients (bug 1564452).
        """
        if not hasattr(self.clients, "storage"):
            self.clients.storage = get_storage_client(
                endpoint_url=self.endpoint_url,
                region_name=self.region,
                read_timeout=settings.S3_READ_TIMEOUT,
                connect_timeout=settings.S3_CONNECT_TIMEOUT,
            )
        return self.clients.storage

    def exists(self) -> bool:
        """Check that this storage exists.

        :returns: True if the storage exists and False if not

        :raises StorageError: an unexpected backend-specific error was raised
        """
        client = self.get_storage_client()

        try:
            client.head_bucket(Bucket=self.name)
        except ClientError as error:
            # A generic ClientError can be raised if:
            # - The bucket doesn't exist (code 404)
            # - The user doesn't have s3:ListBucket perm (code 403)
            # - Other credential issues (code 403, maybe others)
            if error.response["Error"]["Code"] == "404":
                return False
            else:
                raise StorageError(
                    backend=self.backend, url=self.url, error=error
                ) from error
        except BotoCoreError as error:
            raise StorageError(
                backend=self.backend, url=self.url, error=error
            ) from error
        else:
            return True

    def get_object_metadata(self, key: str) -> Optional[ObjectMetadata]:
        """Return object metadata for the object with the given key.

        :arg key: the key of the symbol file not including the prefix, i.e. the key in the format
        ``<debug-file>/<debug-id>/<symbols-file>``.

        :returns: An OjbectMetadata instance if the object exist, None otherwise.

        :raises StorageError: an unexpected backend-specific error was raised
        """
        client = self.get_storage_client()
        # Return 0 if the key can't be found so the memoize cache can cope
        try:
            response = client.head_object(Bucket=self.name, Key=f"{self.prefix}/{key}")
        except ClientError as exception:
            if exception.response["Error"]["Code"] == "404":
                return None
            raise StorageError(
                backend=self.backend, url=self.url, error=exception
            ) from exception
        except BotoCoreError as exception:
            raise StorageError(
                backend=self.backend, url=self.url, error=exception
            ) from exception
        s3_metadata = response.get("Metadata", {})
        original_content_length = s3_metadata.get("original_size")
        if original_content_length is not None:
            try:
                original_content_length = int(original_content_length)
            except ValueError:
                original_content_length = None
        metadata = ObjectMetadata(
            download_url=f"{self.base_url}/{self.prefix}/{quote(key)}",
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
            "Bucket": self.name,
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

        client = self.get_storage_client()
        try:
            client.put_object(**kwargs)
        except (ClientError, BotoCoreError) as exception:
            raise StorageError(
                backend=self.backend, url=self.url, error=exception
            ) from exception


_BOTO3_SESSION_CACHE = threading.local()


def _get_boto3_session() -> boto3.session.Session:
    """Return the boto3 session for the current thread."""
    if not hasattr(_BOTO3_SESSION_CACHE, "session"):
        _BOTO3_SESSION_CACHE.session = boto3.session.Session()
    return _BOTO3_SESSION_CACHE.session


def get_storage_client(endpoint_url=None, region_name=None, **config_params):
    options = {"config": Config(**config_params)}
    if endpoint_url:
        # By default, if you don't specify an endpoint_url
        # boto3 will automatically assume AWS's S3.
        # For local development we are running a local S3
        # fake service with localstack. Then we need to
        # specify the endpoint_url.
        options["endpoint_url"] = endpoint_url
    if region_name:
        options["region_name"] = region_name
    return _get_boto3_session().client("s3", **options)
