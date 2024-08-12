# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import json
from typing import Literal
from unittest import mock

from google.api_core.exceptions import Conflict
from markus.testing import MetricsMock
import pytest
import requests_mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import caches

from tecken.base.symbolstorage import SymbolStorage
from tecken.ext.gcs.storage import GCSStorage
from tecken.ext.s3.storage import S3Storage
from tecken.libmarkus import set_up_metrics
from tecken.libstorage import StorageBackend


def pytest_sessionstart(session):
    set_up_metrics(
        backends=[{"class": "markus.backends.logging.LoggingMetrics"}],
        hostname=settings.HOSTNAME,
        debug=True,
    )


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
    # NOTE(smarnach): Since the Cloud Storage client library is using the requests library, we need
    # to pass real_http=True here to let requests to the GCS emulator through.
    with requests_mock.mock(real_http=True) as m:
        yield m


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
    client = self._get_client()
    client.create_bucket(Bucket=self.bucket)
    response = client.list_objects_v2(Bucket=self.bucket, Prefix=self.prefix)
    for object in response.get("Contents", []):
        client.delete_object(Bucket=self.bucket, Key=object["Key"])


S3Storage.clear = clear_s3_storage


def clear_gcs_storage(self: GCSStorage):
    """Make sure the GCS bucket exists and delete all files under the prefix."""
    # NOTE(smarnach): This gets patched into GCSStorage as a method. I don't want this to exist in
    # production code, since it should never get called there.
    client = self._get_client()
    try:
        client.create_bucket(self.bucket)
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
def get_storage_backend(bucket_name):
    """Return a function to create a unique storage backend for the current test."""

    def _get_storage_backend(
        kind: Literal["gcs", "gcs-cdn", "s3"], try_symbols: bool = False
    ) -> StorageBackend:
        prefix = "try/" * try_symbols + "v1"
        match kind:
            case "gcs":
                return GCSStorage(bucket_name, prefix, try_symbols)
            case "gcs-cdn":
                public_url = f"http://gcs-cdn:8002/{bucket_name}"
                return GCSStorage(
                    bucket_name, prefix, try_symbols, public_url=public_url
                )
            case "s3":
                return S3Storage(bucket_name, prefix, try_symbols)

    return _get_storage_backend


@pytest.fixture(params=["gcs", "gcs-cdn", "s3"])
def symbol_storage_no_create(request, get_storage_backend):
    """Replace the global SymbolStorage instance with a new instance.

    This fixture does not create and clean the storage buckets.
    """
    upload_backend = get_storage_backend(request.param)
    try_upload_backend = get_storage_backend(request.param, try_symbols=True)
    symbol_storage = SymbolStorage(upload_backend, try_upload_backend, [])

    with mock.patch("tecken.base.symbolstorage.SYMBOL_STORAGE", symbol_storage):
        yield symbol_storage


@pytest.fixture
def symbol_storage(symbol_storage_no_create):
    """Replace the global SymbolStorage instance with a new instance with empty backends.

    The storage buckets are created and all objects under the prefix deleted.
    """

    for backend in symbol_storage_no_create.backends:
        backend.clear()
    return symbol_storage_no_create
