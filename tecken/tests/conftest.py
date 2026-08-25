# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import json
from collections.abc import Callable, Iterator
from queue import Empty, Queue
from threading import Event, Thread
from typing import Literal
from unittest import mock

from google.api_core.exceptions import Conflict, NotFound
from google.cloud import pubsub_v1
from markus.testing import MetricsMock
import pytest
import requests_mock

from django.core.cache import caches
from django.db import connections

from tecken.base.symbolstorage import SymbolStorage
from tecken.ext.gcp.storage import GCSStorage
from tecken.libmarkus import set_up_metrics
from tecken.libstorage import StorageBackend
from tecken.upload.management.commands.finalization_worker import (
    run_finalization_worker,
)


def pytest_sessionstart(session):
    from django.conf import settings

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
    from django.contrib.auth.models import Group

    user = django_user_model.objects.create(
        username="uploader", email="uploader@example.com"
    )
    group = Group.objects.get(name="Uploaders")
    user.groups.add(group)
    assert user.has_perm("upload.upload_symbols")
    return user


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


def set_up_gcs_notifications(self: GCSStorage, project: str, topic: str):
    """Create a pub/sub topic and configure GCS notifications."""
    bucket = self._get_bucket()
    # Delete all existing notification configurations first.
    for notification in bucket.list_notifications():
        notification.delete()
    # Create new notification configuration
    bucket.notification(
        topic_project=project,
        topic_name=topic,
        event_types=["OBJECT_FINALIZE"],
        payload_format="JSON_API_V1",
    ).create()


GCSStorage.set_up_notifications = set_up_gcs_notifications


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
        kind: Literal["gcs", "gcs-cdn"], try_symbols: bool = False
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

    return _get_storage_backend


@pytest.fixture(params=["gcs", "gcs-cdn"])
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


@pytest.fixture
def gcs_pubsub_subscription(
    settings,
    bucket_name: str,
    symbol_storage: SymbolStorage,
) -> str:
    """Configure GCS pub/sub notifications and return the subscription name."""
    with (
        pubsub_v1.PublisherClient() as publisher,
        pubsub_v1.SubscriberClient() as subscriber,
    ):
        project_id = settings.PUBSUB_GCP_PROJECT
        # Reuse the bucket name as the pub/sub topic and subscription names
        topic_path = subscriber.topic_path(project_id, bucket_name)
        subscription_path = subscriber.subscription_path(project_id, bucket_name)
        try:
            subscriber.delete_subscription(
                request={"subscription": subscription_path}, timeout=10
            )
        except NotFound:
            pass
        try:
            publisher.delete_topic(request={"topic": topic_path}, timeout=10)
        except NotFound:
            pass
        publisher.create_topic(request={"name": topic_path}, timeout=10)
        subscriber.create_subscription(
            request={"name": subscription_path, "topic": topic_path}, timeout=10
        )
    backend = symbol_storage.get_upload_backend(False)
    backend.set_up_notifications(project_id, bucket_name)
    return bucket_name


@pytest.fixture
def finalization_worker(
    settings, gcs_pubsub_subscription: str
) -> Iterator[Callable[[], None]]:
    """Run a finalization worker for the duration of a test.

    This fixture sets up pub/sub notifications for the bucket belonging to the current test and
    makes the finalization worker listen for these notifications.
    """

    worker_errors: Queue[BaseException] = Queue()
    stop_event = Event()

    def worker_result() -> None:
        try:
            error = worker_errors.get_nowait()
        except Empty:
            return
        raise error.with_traceback(error.__traceback__)

    def worker_target() -> None:
        try:
            run_finalization_worker(stop_event)
        except BaseException as error:
            worker_errors.put(error)

    with (
        mock.patch.dict(
            settings.PUBSUB_QUEUE["options"],
            subscription_name=gcs_pubsub_subscription,
        ),
        # Make sure database connections from the worker get closed immediately.
        mock.patch.dict(connections.settings["default"], CONN_MAX_AGE=0),
    ):
        thread = None
        try:
            thread = Thread(target=worker_target, name="test-finalization-worker")
            thread.start()
            yield worker_result
        finally:
            stop_event.set()
            if thread is not None:
                thread.join(timeout=10)
        if thread is not None and thread.is_alive():
            pytest.fail("finalization worker did not stop within 10 seconds")
        worker_result()
