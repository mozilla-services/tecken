# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import json

import pytest
import boto3
import requests_mock
from moto import mock_s3
from markus.testing import MetricsMock

from django.core.cache import caches


pytest_plugins = ['blockade']


@pytest.fixture
def clear_redis():
    caches['default'].clear()
    caches['store'].clear()


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
def s3_client():
    """Returns a boto3 S3 client instance as a context.
    Usage::

        def test_something(s3_client):
            # create a fixture bucket
            s3_client.create_bucket(Bucket='public')
            # create a fixture object
            s3_client.put_object(...)

            call_code_that_uses_boto3_s3_client()

    """
    mock = mock_s3()
    mock.start()
    yield boto3.client('s3')
    mock.stop()


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
