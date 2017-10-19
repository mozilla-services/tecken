# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import re
from urllib.parse import urlparse

import boto3
from botocore.config import Config


ALL_POSSIBLE_S3_REGIONS = tuple(
    boto3.session.Session().get_available_regions('s3')
)


class S3Bucket:
    """
    Deconstructs a URL about an S3 bucket and breaks it into parts that
    can be used for various purposes. Also, contains a convenient method
    for getting a boto3 s3 client instance ultimately based on the URL.

    Usage::

        >>> s = S3Bucket(
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
        >>> s.s3_client.list_objects_v2(Bucket=s.name, Prefix='some/key.ext')

    """

    def __init__(self, url):
        parsed = urlparse(url)
        self.scheme = parsed.scheme
        self.netloc = parsed.netloc
        try:
            name, prefix = parsed.path[1:].split('/', 1)
            if prefix.endswith('/'):
                prefix = prefix[:-1]
        except ValueError:
            prefix = ''
            name = parsed.path[1:]
        self.name = name
        self.prefix = prefix
        self.private = 'access=public' not in parsed.query
        self.endpoint_url = None
        self.region = None
        if not parsed.netloc.endswith('.amazonaws.com'):
            # the endpoint_url will be all but the path
            self.endpoint_url = f'{parsed.scheme}://{parsed.netloc}'
        region = re.findall(r's3-(.*)\.amazonaws\.com', parsed.netloc)
        if region:
            if region[0] not in ALL_POSSIBLE_S3_REGIONS:
                raise ValueError(f'Not valid S3 region {region[0]}')
            self.region = region[0]

        # This is only created if/when needed
        self._s3_client = None

    @property
    def base_url(self):
        """Return the URL by its domain and bucket name"""
        return '{}://{}/{}'.format(
            self.scheme,
            self.netloc,
            self.name,
        )

    def __repr__(self):
        return (
            f'<{self.__class__.__name__} name={self.name!r} '
            f'endpoint_url={self.endpoint_url!r} region={self.region!r}>'
        )

    @property
    def s3_client(self):
        """return a boto3 session client based on 'self'"""
        if not self._s3_client:
            self._s3_client = get_s3_client(
                endpoint_url=self.endpoint_url,
                region_name=self.region,
            )
        return self._s3_client

    def get_s3_client(self, **config_params):
        """return a boto3 session client with different config parameters"""
        return get_s3_client(
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            **config_params,
        )


def get_s3_client(endpoint_url=None, region_name=None, **config_params):
    options = {
        'config': Config(**config_params),
    }
    if endpoint_url:
        # By default, if you don't specify an endpoint_url
        # boto3 will automatically assume AWS's S3.
        # For local development we are running a local S3
        # fake service with minio. Then we need to
        # specify the endpoint_url.
        options['endpoint_url'] = endpoint_url
    if region_name:
        options['region_name'] = region_name
    session = boto3.session.Session()
    return session.client('s3', **options)
