# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime

import pytest

from django.utils import timezone
from django.contrib.auth.models import User, Permission, Group
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse

from tecken.tokens.models import Token


@pytest.mark.django_db
def test_client_homepage_with_valid_token(client):
    url = reverse('api:auth')
    response = client.get(url)
    assert response.status_code == 200
    assert 'sign_in_url' in response.json()

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    token = Token.objects.create(user=user)

    response = client.get(url, HTTP_AUTH_TOKEN=token.key)
    assert response.status_code == 200
    assert 'sign_in_url' not in response.json()['user']
    assert response.json()['user']['email'] == user.email


@pytest.mark.django_db
def test_client_homepage_with_invalid_token(client):
    url = reverse('api:auth')
    response = client.get(url, HTTP_AUTH_TOKEN='junk')
    assert response.status_code == 403
    assert b'API Token not matched' in response.content

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    token = Token.objects.create(user=user)
    token.expires_at = timezone.now()
    token.save()

    response = client.get(url, HTTP_AUTH_TOKEN=token.key)
    assert response.status_code == 403
    assert b'API Token found but expired' in response.content

    token.expires_at += datetime.timedelta(days=1)
    token.save()
    # but now mess with the user
    user.is_active = False
    user.save()

    response = client.get(url, HTTP_AUTH_TOKEN=token.key)
    assert response.status_code == 403
    assert b'API Token matched but user not active' in response.content


@pytest.mark.django_db
def test_token_permission_signal():
    content_type = ContentType.objects.get(app_label='tokens')
    permission = Permission.objects.create(
        name='Do',
        content_type=content_type,
        codename='do',
    )
    other_permission = Permission.objects.create(
        name='Do Not',
        content_type=content_type,
        codename='donot',
    )

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    token = Token.objects.create(user=user)
    token.permissions.add(permission)
    token.permissions.add(other_permission)

    users = Group.objects.create(name='Users')
    user.groups.add(users)
    users.permissions.add(permission)
    users.permissions.add(other_permission)

    assert token.permissions.all().count() == 2

    # Delete one permission from the group
    users.permissions.remove(other_permission)
    assert token.permissions.all().count() == 1
    assert list(token.permissions.all()) == [permission]
