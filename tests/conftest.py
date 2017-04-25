# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

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
