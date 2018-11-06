# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import re
from urllib.parse import urlparse, urlunparse

from google.cloud import storage
import boto3
from botocore.config import Config

from django.conf import settings


ALL_POSSIBLE_S3_REGIONS = tuple(boto3.session.Session().get_available_regions("s3"))


def scrub_credentials(url):
    """return a URL with any possible credentials removed."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(netloc=parsed.netloc.split("@", 1)[-1]))


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

    def __init__(self, url, try_symbols=False, file_prefix=""):
        parsed = urlparse(url)
        self.scheme = parsed.scheme
        self.netloc = parsed.netloc
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
        if "googleapis" in parsed.netloc:
            self.endpoint_url = scrub_credentials(url)
        elif not parsed.netloc.endswith(".amazonaws.com"):
            # the endpoint_url will be all but the path
            self.endpoint_url = f"{parsed.scheme}://{parsed.netloc}"
        region = re.findall(r"s3-(.*)\.amazonaws\.com", parsed.netloc)
        if region:
            if region[0] not in ALL_POSSIBLE_S3_REGIONS:
                raise ValueError(f"Not valid S3 region {region[0]}")
            self.region = region[0]

    @property
    def is_google_cloud_storage(self):
        return "googleapis" in self.netloc

    @property
    def base_url(self):
        """Return the URL by its domain and bucket name"""
        return "{}://{}/{}".format(self.scheme, self.netloc, self.name)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} name={self.name!r} "
            f"endpoint_url={self.endpoint_url!r} region={self.region!r} "
            f"is_google_cloud_storage={self.is_google_cloud_storage}>"
        )

    @property
    def client(self):
        """return a boto3 session client based on 'self'"""
        if not getattr(self, "_client", None):
            self._client = get_storage_client(
                endpoint_url=self.endpoint_url,
                region_name=self.region,
                is_google_cloud_storage=self.is_google_cloud_storage,
            )
        return self._client

    def get_storage_client(self, **config_params):
        """return a boto3 session client with different config parameters"""
        return get_storage_client(
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            is_google_cloud_storage=self.is_google_cloud_storage,
            **config_params,
        )

    def get_or_load_bucket(self):
        if not hasattr(self, "_bucket"):
            assert self.is_google_cloud_storage
            self._bucket = self.client.get_bucket(self.name)
        return self._bucket


def get_storage_client(
    endpoint_url=None, region_name=None, is_google_cloud_storage=False, **config_params
):
    if is_google_cloud_storage:
        client = storage.Client.from_service_account_json(
            settings.GOOGLE_APPLICATION_CREDENTIALS
        )
        return client
    else:
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
