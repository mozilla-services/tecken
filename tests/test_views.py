# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os

import pytest
import mock

from django.core.urlresolvers import reverse
from django.core.cache import cache

from tecken.tasks import sample_task
from tecken.views import (
    handler500,
    handler400,
    handler403,
)


@pytest.mark.django_db
def test_client_task_tester(client, clear_redis_store):
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


def test_dashboard(client, settings, tmpdir):
    settings.STATIC_ROOT = tmpdir
    with open(os.path.join(tmpdir, 'index.html'), 'wb') as f:
        f.write(
            b"""<html>
            <h1>Hi!</h1>
            </html>"""
        )
    response = client.get('/')
    assert response.status_code == 200
    assert response['content-type'] == 'text/html'
    html = response.getvalue()
    assert b'<h1>Hi!</h1>' in html


def test_frontend_index_html_redirect(client, settings, tmpdir):
    # If you hit this URL with '/index.html' explicit it redirects.
    # But only if there is no 'index.html' file in settings.STATIC_ROOT.
    settings.STATIC_ROOT = tmpdir
    response = client.get('/index.html')
    assert response.status_code == 302
    assert response['location'] == '/'


def test_frontend_index_html_aliases(client, settings, tmpdir):
    settings.STATIC_ROOT = tmpdir
    with open(os.path.join(tmpdir, 'index.html'), 'wb') as f:
        f.write(
            b"""<html>
            <h1>React Routing!</h1>
            </html>"""
        )
    # For example `/help` is a route taking care of in the React app.
    response = client.get('/help')
    assert response.status_code == 200
    assert response['content-type'] == 'text/html'

    response = client.get('/neverheardof')
    assert response.status_code == 404


def test_sample_task(clear_redis_store):
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


def test_handler404(client):
    # This handler is best tested as an integration test because
    # it's a lot easier to simulate.
    response = client.get('/blabla')
    assert response.status_code == 404
    assert response['Content-type'] == 'application/json'
    information = json.loads(response.content.decode('utf-8'))
    assert information['error']
    assert information['path'] == '/blabla'
