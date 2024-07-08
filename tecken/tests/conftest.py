# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import io
import json
import os
from typing import Literal
from unittest import mock

import boto3
import botocore
from botocore.client import ClientError, Config
from google.api_core.exceptions import Conflict
from markus.testing import MetricsMock
import pytest
import requests_mock

from django.contrib.auth.models import Group
from django.core.cache import caches

from tecken.base.symbolstorage import SymbolStorage
from tecken.libstorage import StorageBackend
from tecken.ext.gcs.storage import GCSStorage
from tecken.ext.s3.storage import S3Storage


@pytest.fixture(autouse=True)
def clear_cache():
    caches["default"].clear()


@pytest.fixture
def json_poster(client):
    """
    Uses the client instance to make a client.post() call with the 'data'
    as a valid JSON string with the right header.
    """

    def inner(url, data, **extra):
        debug = extra.pop("debug", None)
        options = extra.pop("options", False)
        if not isinstance(data, str):
            data = json.dumps(data)
        extra["content_type"] = "application/json"
        if debug is not None:
            extra["HTTP_DEBUG"] = str(debug)
        if options:
            return client.options(url, data, **extra)
        else:
            return client.post(url, data, **extra)

    return inner


@pytest.fixture
def metricsmock():
    """Returns a MetricsMock context to record metrics records

    Usage::

        def test_something(metricsmock):
            # do test stuff...

            mm.print_records()  # debugging tests

            mm.assert_incr("some.stat", tags=["sometag:fred"])

    """
    with MetricsMock() as mm:
        yield mm


@pytest.fixture
def requestsmock():
    """Return a context where requests are all mocked.
    Usage::

        def test_something(requestsmock):
            requestsmock.get(
                'https://example.com/path'
                content=b'The content'
            )
            # Do stuff that involves requests.get('http://example.com/path')
    """
    with requests_mock.mock() as m:
        yield m


_orig_make_api_call = botocore.client.BaseClient._make_api_call


@pytest.fixture
def botomock():
    """Return a class that can be used as a context manager when called.
    Usage::

        def test_something(botomock):

            def my_make_api_call(self, operation_name, api_params):
                if random.random() > 0.5:
                    from botocore.exceptions import ClientError
                    parsed_response = {
                        'Error': {'Code': '403', 'Message': 'Not found'}
                    }
                    raise ClientError(parsed_response, operation_name)
                else:
                    return {
                        'CustomS3': 'Headers',
                    }

            with botomock(my_make_api_call):
                ...things that depend on boto3...

                # You can also, whilst debugging on tests,
                # see what calls where made.
                # This is handy to see and assert that your replacement
                # method really was called.
                print(botomock.calls)

    Whilst working on a test, you might want wonder "What would happen"
    if I let this actually use the Internet to make the call un-mocked.
    To do that use ``botomock.orig()``. For example::

        def test_something(botomock):

            def my_make_api_call(self, operation_name, api_params):
                if api_params == something:
                    ...you know what to do...
                else:
                    # Only in test debug mode
                    result = botomock.orig(self, operation_name, api_params)
                    print(result)
                    raise NotImplementedError

    """

    class BotoMock:
        def __init__(self):
            self.calls = []

        def __call__(self, mock_function):
            def wrapper(f):
                def inner(*args, **kwargs):
                    self.calls.append(args[1:])
                    return f(*args, **kwargs)

                return inner

            return mock.patch(
                "botocore.client.BaseClient._make_api_call", new=wrapper(mock_function)
            )

        def orig(self, *args, **kwargs):
            return _orig_make_api_call(*args, **kwargs)

    return BotoMock()


class S3Helper:
    """S3 helper class.

    When used in a context, this will clean up any buckets created.

    """

    def __init__(self):
        self._buckets_seen = None
        self.conn = self.get_client()

    def get_client(self):
        session = boto3.session.Session(
            # NOTE(willkg): these use environment variables set in
            # docker/config/test.env
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )
        client = session.client(
            service_name="s3",
            config=Config(s3={"addressing_style": "path"}),
            endpoint_url=os.environ["AWS_ENDPOINT_URL"],
        )
        return client

    def __enter__(self):
        self._buckets_seen = set()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        for bucket in self._buckets_seen:
            # Delete any objects in the bucket
            resp = self.conn.list_objects(Bucket=bucket)
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                self.conn.delete_object(Bucket=bucket, Key=key)

            # Then delete the bucket
            self.conn.delete_bucket(Bucket=bucket)
        self._buckets_seen = None

    def create_bucket(self, bucket_name):
        """Create specified bucket if it doesn't exist."""
        try:
            self.conn.head_bucket(Bucket=bucket_name)
        except ClientError:
            self.conn.create_bucket(Bucket=bucket_name)
        if self._buckets_seen is not None:
            self._buckets_seen.add(bucket_name)

    def upload_fileobj(self, bucket_name, key, data):
        """Puts an object into the specified bucket."""
        self.create_bucket(bucket_name)
        self.conn.upload_fileobj(Fileobj=io.BytesIO(data), Bucket=bucket_name, Key=key)

    def download_fileobj(self, bucket_name, key):
        """Fetches an object from the specified bucket"""
        self.create_bucket(bucket_name)
        resp = self.conn.get_object(Bucket=bucket_name, Key=key)
        return resp["Body"].read()

    def list(self, bucket_name):
        """Return list of keys for objects in bucket."""
        self.create_bucket(bucket_name)
        resp = self.conn.list_objects(Bucket=bucket_name)
        return [obj["Key"] for obj in resp["Contents"]]


@pytest.fixture
def s3_helper():
    """Returns an S3Helper for automating repetitive tasks in S3 setup.

    Provides:

    * ``get_client()``
    * ``create_bucket(bucket_name)``
    * ``upload_fileobj(bucket_name, key, value)``
    * ``download_fileobj(bucket_name, key)``
    * ``list(bucket_name)``

    """
    with S3Helper() as s3_helper:
        yield s3_helper


@pytest.fixture
def fakeuser(django_user_model):
    """Creates and returns a fake regular user."""
    return django_user_model.objects.create(username="fake", email="fake@example.com")


@pytest.fixture
def uploaderuser(django_user_model):
    """Creates and returns a fake user in the uploaders group."""
    user = django_user_model.objects.create(
        username="uploader", email="uploader@example.com"
    )
    group = Group.objects.get(name="Uploaders")
    user.groups.add(group)
    assert user.has_perm("upload.upload_symbols")
    return user


def clear_s3_storage(self: S3Storage):
    """Make sure the S3 bucket exists and delete all files under the prefix."""
    # NOTE(smarnach): This gets patched into S3Storage as a method. I don't want this to exist in
    # production code, since it should never get called there.
    client = self.get_storage_client()
    client.create_bucket(Bucket=self.name)
    response = client.list_objects_v2(Bucket=self.name, Prefix=self.prefix)
    for object in response.get("Contents", []):
        client.delete_object(Bucket=self.name, Key=object["Key"])


S3Storage.clear = clear_s3_storage


def clear_gcs_storage(self: GCSStorage):
    """Make sure the GCS bucket exists and delete all files under the prefix."""
    # NOTE(smarnach): This gets patched into GCSStorage as a method. I don't want this to exist in
    # production code, since it should never get called there.
    client = self._get_client()
    try:
        client.create_bucket(self.name)
    except Conflict:
        # Bucket already exists.
        pass
    bucket = self._get_bucket()
    blobs = bucket.list_blobs(prefix=self.prefix, fields="items(name)")
    bucket.delete_blobs(list(blobs))


GCSStorage.clear = clear_gcs_storage


@pytest.fixture
def bucket_name(request):
    """A unique bucket name for the currently running test.

    Using a different bucket for each test node prevents interaction between tests. The bucket name
    is based on the test node id, so it's stable across test runs.
    """
    hash = hashlib.md5(request.node.nodeid.encode()).hexdigest()
    return f"test-{hash}"


@pytest.fixture
def get_test_storage_url(bucket_name):
    """Return a function to generate unique test storage URLs for the current test."""

    def _get_test_storage_url(
        kind: Literal["gcs", "s3"], try_symbols: bool = False
    ) -> str:
        match kind:
            case "gcs":
                url = f"http://gcs-emulator:8001/{bucket_name}"
            case "s3":
                url = f"http://localstack:4566/{bucket_name}"
        if try_symbols:
            url += "/try"
        return url

    return _get_test_storage_url


@pytest.fixture
def create_storage_backend(get_test_storage_url):
    """Return a function to create storage backends."""
    # NOTE(smarnach): This fixture is meant to replace S3Helper for backend-agnostic tests.
    # We don't need to delete buckets after running tests. Each test gets a unique bucket that's
    # cleared before running the test.

    def _create_storage_backend(
        kind: Literal["gcs", "s3"], try_symbols: bool = False
    ) -> StorageBackend:
        """Create a new StorageBackend instance and make sure the underlying storage exists."""
        url = get_test_storage_url(kind, try_symbols)
        backend = StorageBackend.new(url, try_symbols)
        backend.clear()
        return backend

    return _create_storage_backend


@pytest.fixture(params=["gcs", "s3"])
def symbol_storage(request, settings, get_test_storage_url):
    """Replace the global SymbolStorage instance with a new instance with empty backends"""

    settings.UPLOAD_DEFAULT_URL = get_test_storage_url(request.param)
    settings.SYMBOL_URLS = []
    settings.UPLOAD_TRY_SYMBOLS_URL = get_test_storage_url(
        request.param, try_symbols=True
    )
    symbol_storage = SymbolStorage.from_settings()
    for backend in symbol_storage.backends:
        backend.clear()

    with mock.patch("tecken.base.symbolstorage.SYMBOL_STORAGE", symbol_storage):
        yield symbol_storage
