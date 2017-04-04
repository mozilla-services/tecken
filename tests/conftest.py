import json

import pytest

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
