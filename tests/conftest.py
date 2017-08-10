# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import json

import pytest
import mock
import requests_mock
import botocore
from markus.testing import MetricsMock

from django.core.cache import caches
from django.contrib.auth.models import User

pytest_plugins = ['blockade']


@pytest.fixture
def clear_redis():
    caches['default'].clear()
    caches['store'].clear()


@pytest.fixture
def clear_cache():
    caches['default'].clear()


@pytest.fixture(autouse=True)
def clear_local_cache():
    """autouse=True fixtures (fixtures that get used in every test in
    the module) are generally best avoided. However, this one is so
    light and useful because it clears the global cache object."""
    caches['local'].clear()


@pytest.fixture
def json_poster(client):
    """
    Uses the client instance to make a client.post() call with the 'data'
    as a valid JSON string with the right header.
    """
    def inner(url, data, **extra):
        if not isinstance(data, str):
            data = json.dumps(data)
        extra['content_type'] = 'application/json'
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
        'broker_url': 'redis://redis-cache:6379/0',
        'result_backend': 'redis://redis-cache:6379/0',
        'task_always_eager': True,
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
                'botocore.client.BaseClient._make_api_call',
                new=wrapper(mock_function)
            )

        def orig(self, *args, **kwargs):
            return _orig_make_api_call(*args, **kwargs)

    return BotoMock()


@pytest.fixture
def fakeuser():
    return User.objects.create(
        username='peterbe',
        email='peterbe@example.com',
    )
