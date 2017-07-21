# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from django.contrib.auth.models import User, Permission, Group
from django.core.urlresolvers import reverse
from django.utils import timezone

from tecken.tokens.models import Token
from tecken.upload.models import Upload


@pytest.mark.django_db
def test_auth(client):
    url = reverse('api:auth')
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert not data.get('user')
    assert data['sign_in_url']

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['user']['is_active']
    assert data['user']['email']
    assert data['sign_out_url']


@pytest.mark.django_db
def test_tokens(client):
    url = reverse('api:tokens')
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['tokens'] == []
    assert data['permissions'] == []

    # Let's try again, but this time give the user some permissions
    # and existing tokens.

    permission = Permission.objects.get(codename='upload_symbols')
    user.user_permissions.add(permission)

    token = Token.objects.create(
        user=user,
        notes='hej!',
    )
    token.permissions.add(permission)

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()

    dt, = data['tokens']
    assert dt['id'] == token.id
    assert dt['key'] == token.key
    assert dt['notes'] == token.notes
    assert not dt['is_expired'] == token.key
    # Can't just compare with .isoformat() since DjangoJSONEncoder
    # does special things with the timezone
    assert dt['expires_at'][:20] == token.expires_at.isoformat()[:20]
    assert dt['permissions'] == [
        {
            'id': permission.id,
            'name': permission.name,
        }
    ]

    assert data['permissions'] == [
        {
            'id': permission.id,
            'name': permission.name,
        }
    ]


@pytest.mark.django_db
def test_tokens_create(client):
    url = reverse('api:tokens')
    response = client.post(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.post(url)
    assert response.status_code == 400
    assert response.json()['errors']['permissions']
    assert response.json()['errors']['expires']

    permission = Permission.objects.get(codename='upload_symbols')
    user.user_permissions.add(permission)
    response = client.post(url, {
        'permissions': str(permission.id),
        'expires': 'notaninteger',
    })
    assert response.status_code == 400
    assert response.json()['errors']['expires']

    not_your_permission = Permission.objects.get(codename='view_all_uploads')
    response = client.post(url, {
        'permissions': str(not_your_permission.id),
        'expires': '10',
    })
    assert response.status_code == 403
    assert response.json()['errors']['permissions']

    response = client.post(url, {
        'permissions': str(permission.id),
        'expires': '10',
        'notes': 'Hey man!  ',
    })
    assert response.status_code == 201
    token = Token.objects.get(notes='Hey man!')
    future = token.expires_at - timezone.now()
    # due to rounding, we can't compare the seconds as equals
    epsilon = abs(
        future.total_seconds() - 10 * 24 * 60 * 60
    )
    assert epsilon < 1
    assert permission in token.permissions.all()


@pytest.mark.django_db
def test_tokens_delete(client):
    url = reverse('api:delete_token', args=(9999999,))
    response = client.post(url)
    assert response.status_code == 405

    response = client.delete(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.delete(url)
    assert response.status_code == 404

    # Create an actual token that can be deleted
    token = Token.objects.create(user=user)
    url = reverse('api:delete_token', args=(token.id,))
    response = client.delete(url)
    assert response.status_code == 200
    assert not Token.objects.filter(user=user)

    # Try to delete someone else's token and it should fail
    other_user = User.objects.create(username='other')
    token = Token.objects.create(user=other_user)
    url = reverse('api:delete_token', args=(token.id,))
    response = client.delete(url)
    assert response.status_code == 404

    # ...but works if you're a superuser
    user.is_superuser = True
    user.save()
    response = client.delete(url)
    assert response.status_code == 200
    assert not Token.objects.filter(user=other_user)


@pytest.mark.django_db
def test_users(client):
    url = reverse('api:users')
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.is_superuser = True
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get(url)
    assert response.status_code == 200
    found_user, = response.json()['users']
    assert found_user['email'] == user.email

    group = Group.objects.get(name='Uploaders')
    user.groups.add(group)
    Upload.objects.create(
        user=user,
        size=1234,
    )
    Token.objects.create(
        user=user,
    )
    response = client.get(url)
    assert response.status_code == 200
    found_user, = response.json()['users']
    assert found_user['no_tokens'] == 1
    assert found_user['no_uploads'] == 1
    assert found_user['groups'][0]['name'] == 'Uploaders'
    assert found_user['permissions'][0]['name'] == 'Upload Symbols Files'


@pytest.mark.django_db
def test_edit_user(client):
    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    url = reverse('api:edit_user', args=(user.id,))
    response = client.get(url)
    assert response.status_code == 403

    user.is_superuser = True
    user.save()
    group = Group.objects.get(name='Uploaders')
    user.groups.add(group)
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()['groups']
    assert response.json()['user']['groups'][0]['name'] == 'Uploaders'

    new_group = Group.objects.create(name='New Group')
    response = client.post(url, {
        'groups': 'JUNK',
        'is_active': False,
        'is_superuser': True,
    })
    assert response.status_code == 400

    response = client.post(url, {
        'groups': new_group.id,
        'is_active': False,
        'is_superuser': True,
    })
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.groups.all().count() == 1
    assert not user.is_active
    assert user.is_superuser

    # Now that we're inactive, we can't GET any more.
    # We've basically locked ourselves out. Nuts but should work.
    response = client.get(url)
    assert response.status_code == 403
