# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from io import StringIO

import pytest
from markus import TIMING

from django.core.management.base import CommandError
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse


@pytest.mark.django_db
def test_superuser_command():
    stdout = StringIO()
    call_command(
        'superuser',
        'foo@example.com',
        stdout=stdout,
    )
    output = stdout.getvalue()
    assert 'User created' in output
    assert 'PROMOTED to superuser' in output
    assert User.objects.get(email='foo@example.com', is_superuser=True)

    # all it a second time
    stdout = StringIO()
    call_command(
        'superuser',
        'foo@example.com',
        stdout=stdout,
    )
    output = stdout.getvalue()
    assert 'User created' not in output
    assert 'DEMOTED to superuser' in output
    assert User.objects.get(email='foo@example.com', is_superuser=False)

    with pytest.raises(CommandError):
        stdout = StringIO()
        call_command(
            'superuser',
            'gibberish',
            stdout=stdout,
        )


@pytest.mark.django_db
def test_is_blocked_in_auth0_command(requestsmock):
    requestsmock.post(
        'https://auth.example.com/oauth/token',
        json={'access_token': 'whatever'},
        status_code=200,
    )

    requestsmock.get(
        'https://auth.example.com/api/v2/users?q=email%3A%22'
        'not%40example.com%22',
        json=[{'name': 'Not'}],
        status_code=200,
    )

    stdout = StringIO()
    call_command(
        'is-blocked-in-auth0',
        'not@example.com',
        stdout=stdout,
    )
    output = stdout.getvalue()
    assert 'NOT blocked' in output

    requestsmock.get(
        'https://auth.example.com/api/v2/users?q=email%3A%22'
        'blocked%40example.com%22',
        json=[{'name': 'Something', 'blocked': True}],
        status_code=200,
    )

    stdout = StringIO()
    call_command(
        'is-blocked-in-auth0',
        'blocked@example.com',
        stdout=stdout,
    )
    output = stdout.getvalue()
    assert 'BLOCKED!' in output

    requestsmock.get(
        'https://auth.example.com/api/v2/users?q=email%3A%22'
        'notfound%40example.com%22',
        json=[],
        status_code=200,
    )
    stdout = StringIO()
    call_command(
        'is-blocked-in-auth0',
        'notfound@example.com',
        stdout=stdout,
    )
    output = stdout.getvalue()
    assert 'could not be found' in output

    with pytest.raises(CommandError):
        stdout = StringIO()
        call_command(
            'is-blocked-in-auth0',
            'gibberish',
            stdout=stdout,
        )


@pytest.mark.django_db
def test_not_blocked_in_auth0(client, requestsmock, settings, metricsmock):
    settings.ENABLE_AUTH0_BLOCKED_CHECK = True

    url = reverse('api:auth')
    response = client.get(url)
    # No requestsmocking needed yet because the client is anonymous
    assert response.status_code == 200

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    requestsmock.post(
        'https://auth.example.com/oauth/token',
        json={'access_token': 'whatever'},
        status_code=200,
    )

    requestsmock.get(
        'https://auth.example.com/api/v2/users?q=email%3A%22'
        'peterbe%40example.com%22',
        json=[{'name': 'Fine', 'blocked': False}],
        status_code=200,
    )

    response = client.get(url)
    assert response.status_code == 200

    metrics_records = metricsmock.get_records()
    timing_record, = metrics_records
    assert timing_record[0] == TIMING


@pytest.mark.django_db
def test_blocked_in_auth0(client, requestsmock, settings, clear_redis_store):
    settings.ENABLE_AUTH0_BLOCKED_CHECK = True

    url = reverse('api:auth')
    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    requestsmock.post(
        'https://auth.example.com/oauth/token',
        json={'access_token': 'whatever'},
        status_code=200,
    )

    requestsmock.get(
        'https://auth.example.com/api/v2/users?q=email%3A%22'
        'peterbe%40example.com%22',
        json=[{'name': 'Fine', 'blocked': True}],
        status_code=200,
    )

    response = client.get(url)
    assert response.status_code == 403

    user.refresh_from_db()
    assert not user.is_active
