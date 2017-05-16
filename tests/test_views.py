# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from django.core.urlresolvers import reverse
from django.core.cache import cache

from tecken.tasks import sample_task


@pytest.mark.django_db
def test_client_task_tester(client, clear_redis, celery_worker):
    url = reverse('task_tester')
    response = client.get(url)
    assert response.status_code == 400
    assert b'Make a POST request to this URL first' in response.content

    response = client.post(url)
    assert response.status_code == 201
    assert b'Now make a GET request to this URL' in response.content

    response = client.get(url)
    assert response.status_code == 200
    assert b'It works!' in response.content


def test_sample_task(clear_redis):
    sample_task('foo', 'bar', 1)
    cache.get('foo') == 'bar'
