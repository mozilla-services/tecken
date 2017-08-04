# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import json

import pytest
import mock

from django.core.urlresolvers import reverse
from django.core.cache import cache

from tecken.tasks import sample_task
from tecken.views import (
    handler500,
    handler400,
    handler403,
    handler404,
)


@pytest.mark.django_db
def test_client_task_tester(client, clear_redis):
    url = reverse('task_tester')

    def fake_task(key, value, expires):
        cache.set(key, value, expires)

    _mock_function = 'tecken.views.sample_task.delay'
    with mock.patch(_mock_function, new=fake_task):

        response = client.get(url)
        assert response.status_code == 400
        assert b'Make a POST request to this URL first' in response.content

        response = client.post(url)
        assert response.status_code == 201
        assert b'Now make a GET request to this URL' in response.content

        response = client.get(url)
        assert response.status_code == 200
        assert b'It works!' in response.content


@pytest.mark.django_db
def test_dashboard(client):
    response = client.get('/')
    assert response.status_code == 200
    information = response.json()
    assert 'documentation' in information


def test_sample_task(clear_redis):
    sample_task('foo', 'bar', 1)
    cache.get('foo') == 'bar'


def test_contribute_json(client):
    url = reverse('contribute_json')
    response = client.get(url)
    assert response.status_code == 200
    # No point testing that the content can be deserialized because
    # the view would Internal Server Error if the ./contribute.json
    # file on disk is invalid.
    assert response['Content-type'] == 'application/json'


def test_handler500(rf):
    request = rf.get('/')
    response = handler500(request)
    assert response.status_code == 500
    assert response['Content-type'] == 'application/json'
    assert json.loads(response.content.decode('utf-8'))['error']


def test_handler400(rf):
    request = rf.get('/')
    response = handler400(request)
    assert response.status_code == 400
    assert response['Content-type'] == 'application/json'
    assert json.loads(response.content.decode('utf-8'))['error']


def test_handler403(rf):
    request = rf.get('/')
    response = handler403(request)
    assert response.status_code == 403
    assert response['Content-type'] == 'application/json'
    assert json.loads(response.content.decode('utf-8'))['error']


def test_handler404(rf):
    request = rf.get('/')
    response = handler404(request)
    assert response.status_code == 404
    assert response['Content-type'] == 'application/json'
    assert json.loads(response.content.decode('utf-8'))['error']
