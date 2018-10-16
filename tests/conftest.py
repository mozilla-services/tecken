# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import json
import tempfile

import pytest
import mock
import requests_mock
import botocore
from markus.testing import MetricsMock

from django.core.cache import caches
from django.contrib.auth.models import User

pytest_plugins = ["blockade"]


@pytest.fixture
def clear_redis_store():
    caches["store"].clear()


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
        if not isinstance(data, str):
            data = json.dumps(data)
        extra["content_type"] = "application/json"
        if debug is not None:
            extra["HTTP_DEBUG"] = str(debug)
        return client.post(url, data, **extra)

    return inner


@pytest.fixture
def metricsmock():
    """Returns a MetricsMock context to record metrics records
    Usage::
        def test_something(metricsmock):
            # do test stuff...

            mm.print_records()  # debugging tests

            assert mm.has_record(
                stat='some.stat',
                kwargs_contains={
                    'something': 1
                }
            )
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


@pytest.fixture
def celery_config():
    return {
        "broker_url": "redis://redis-cache:6379/0",
        "result_backend": "redis://redis-cache:6379/0",
        "task_always_eager": True,
    }


# This needs to be imported at least once. Otherwise the mocking
# done in botomock() doesn't work.
# (peterbe) Would like to know why but for now let's just comply.
import boto3  # noqa

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


@pytest.fixture
def gcsmock():
    """Return a class where the fundamental google-cloud-storage client has been
    mocked."""

    # XXX can this move?
    from google.cloud.storage.client import Client
    from google.cloud.storage.bucket import Bucket

    class MockBucket(Bucket):
        def __init__(self, name=None):
            # Basically, ignore everything.
            self.name = name

        def get_blob(self, key):
            raise NotImplementedError("You're supposed to set this yourself.")

        def blob(self, key):
            raise NotImplementedError("You're supposed to set this yourself.")

    class MockBlob:
        def __init__(self, key, **options):
            self.key = key
            self.size = options.get("size", None)
            self.metadata = options.get("metadata", None)
            self.content_encoding = None
            self.content_type = None
            self.public_url = f"https://googleapis.example.com/bucket/{key}"

        def upload_from_file(self, file):
            # By default we pretend the upload worked.
            # You can override this if you want to simulate other experiences
            # or do assertions on the file sent in to it.
            pass

    # Inherit from google.cloud.storage.client.Client so it works to do things
    # like...:
    #
    #     if isinstance(storage_client, google.cloud.storage.Client):
    #         ...
    #
    class MockClient(Client):
        def __init__(self, *args, **kwargs):
            # Basically, ignore everything.
            pass

        def from_service_account_json(self, *args, **kwargs):
            return self

        def mock_blob_factory(self, key, **options):
            return MockBlob(key, **options)

    new_client = MockClient()

    # Pass along the useful MockBlob class inside the client. Yes, it's a bit weird
    # but the advantage is that you only need this one pytest ficture to
    # get a thing that mock patches google.cloud.storage.Client AND it also has
    # useful tools for creating mocked buckets and blobs etc.
    new_client.MockBlob = MockBlob
    # Same justification for passig along the MockBucket
    new_client.MockBucket = MockBucket

    with mock.patch("google.cloud.storage.Client", new=new_client):
        yield new_client


@pytest.fixture
def fakeuser():
    return User.objects.create(username="peterbe", email="peterbe@example.com")


@pytest.fixture
def tmpdir():
    """Yields a temporary directory that gets deleted at the end of the test.
    Usage::

        def test_something(tmpdir):
            with open(os.path.join(tmpdir, 'index.html'), 'wb') as f:
                f.write(b'Stuff!')
                ...

    """
    with tempfile.TemporaryDirectory() as d:
        yield d


def _mock_invalidate_symbolicate_cache(function_path):
    class FakeTask:
        all_delay_arguments = []

        def delay(self, *args, **kwargs):
            self.all_delay_arguments.append((args, kwargs))

    fake_task = FakeTask()

    with mock.patch(function_path, new=fake_task):
        yield fake_task


@pytest.fixture
def upload_mock_invalidate_symbolicate_cache():
    """Yields an object that is the mocking substitute of some task
    functions that are imported by the views.
    If a view function (that you know your test will execute) depends
    on 'tecken.symbolicate.tasks.invalidate_symbolicate_cache', add
    this fixture to your test. Then you can access all the arguments
    sent to it as `.delay()` arguments and keyword arguments.
    """

    class FakeTask:
        all_delay_arguments = []

        def delay(self, *args, **kwargs):
            self.all_delay_arguments.append((args, kwargs))

    fake_task = FakeTask()

    _mock_function = "tecken.upload.views.invalidate_symbolicate_cache_task"
    with mock.patch(_mock_function, new=fake_task):
        yield fake_task


@pytest.fixture
def upload_mock_update_uploads_created_task():
    """Yields an object that is the mocking substitute of some task
    functions that are imported by the views.
    If a view function (that you know your test will execute) depends
    on 'tecken.upload.tasks.update_uploads_created_task', add
    this fixture to your test. Then you can access all the arguments
    sent to it as `.delay()` arguments and keyword arguments.
    """

    class FakeTask:
        all_delay_arguments = []

        def delay(self, *args, **kwargs):
            self.all_delay_arguments.append((args, kwargs))

    fake_task = FakeTask()

    _mock_function = "tecken.upload.views.update_uploads_created_task"
    with mock.patch(_mock_function, new=fake_task):
        yield fake_task
