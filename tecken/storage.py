# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import re
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError
import boto3
from botocore.config import Config

from django.conf import settings


ALL_POSSIBLE_S3_REGIONS = tuple(boto3.session.Session().get_available_regions("s3"))


class StorageError(Exception):
    """A backend-specific client reported an error."""

    def __init__(self, bucket, backend_error):
        self.backend = bucket.backend
        self.url = bucket.url
        self.backend_msg = f"{type(backend_error).__name__}: {backend_error}"

    def __str__(self):
        return f"{self.backend} backend ({self.url}) raised {self.backend_msg}"


class StorageBucket:
    """
    Deconstructs a URL about an S3 bucket and breaks it into parts that
    can be used for various purposes. Also, contains a convenient method
    for getting a boto3 s3 client instance ultimately based on the URL.

    Usage::

        >>> s = StorageBucket(
        ...    'https://s3-us-west-2.amazonaws.com/bucky/prfx?access=public'
        )
        >>> s.netloc
        's3-us-west-2.amazonaws.com'
        >>> s.name
        'bucky'
        >>> s.private  # note, private is usually default
        False
        >>> s.prefix
        'prfx'
        >>> s.client.list_objects_v2(Bucket=s.name, Prefix='some/key.ext')

    """

    # A substring match of the domain is used to recognize storage backends.
    # For emulated backends, the name should be present in the docker-compose
    # service name.
    _URL_FINGERPRINT = {
        # AWS S3, like bucket-name.s3.amazonaws.com
        "s3": ".amazonaws.com",
        # Minio S3 Emulator
        "emulated-s3": "minio",
        # S3 test domain
        "test-s3": "s3.example.com",
    }

    def __init__(self, url, try_symbols=False, file_prefix=""):
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
        self.private = "access=public" not in parsed.query
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

    @property
    def base_url(self):
        """Return the URL by its domain and bucket name"""
        return f"{self.scheme}://{self.netloc}/{self.name}"

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} name={self.name!r} "
            f"endpoint_url={self.endpoint_url!r} region={self.region!r} "
            f"backend={self.backend!r}>"
        )

    @property
    def client(self):
        """Return a backend-specific client, cached on first access.

        TODO(jwhitlock): Build up StorageBucket API so users don't work directly with
        the backend-specific clients (bug 1564452).
        """
        if not getattr(self, "_client", None):
            self._client = get_storage_client(
                endpoint_url=self.endpoint_url, region_name=self.region
            )
        return self._client

    def get_storage_client(self, **config_params):
        """Return a backend-specific client, overriding default config parameters.

        TODO(jwhitlock): Build up StorageBucket API so users don't work directly with
        the backend-specific clients (bug 1564452).
        """
        return get_storage_client(
            endpoint_url=self.endpoint_url, region_name=self.region, **config_params
        )

    def exists(self):
        """Check that the bucket exists in the backend.

        :raises StorageError: An unexpected backed-specific error was raised.
        :returns: True if the bucket exists, False if it does not
        """
        # Use lower lookup timeouts on S3, to fail quickly when there are network issues
        client = self.get_storage_client(
            read_timeout=settings.S3_LOOKUP_READ_TIMEOUT,
            connect_timeout=settings.S3_LOOKUP_CONNECT_TIMEOUT,
        )

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
                raise StorageError(self, error)
        except BotoCoreError as error:
            raise StorageError(self, error)
        else:
            return True


def get_storage_client(endpoint_url=None, region_name=None, **config_params):
    options = {"config": Config(**config_params)}
    if endpoint_url:
        # By default, if you don't specify an endpoint_url
        # boto3 will automatically assume AWS's S3.
        # For local development we are running a local S3
        # fake service with minio. Then we need to
        # specify the endpoint_url.
        options["endpoint_url"] = endpoint_url
    if region_name:
        options["region_name"] = region_name
    session = boto3.session.Session()
    return session.client("s3", **options)
