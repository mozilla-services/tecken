# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime
from io import StringIO

import pytest

from django.contrib.auth.models import User, Permission, Group
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from tecken.tokens.models import make_key, Token


@pytest.mark.django_db
def test_createtoken_no_key_command():
    assert Token.objects.all().count() == 0
    stdout = StringIO()
    call_command("superuser", "foo@example.com", stdout=stdout)
    stdout = StringIO()
    call_command("createtoken", "foo@example.com", stdout=stdout)

    assert Token.objects.all().count() == 1


@pytest.mark.django_db
def test_createtoken_with_key_command():
    assert Token.objects.all().count() == 0
    stdout = StringIO()
    call_command("superuser", "foo@example.com", stdout=stdout)
    stdout = StringIO()
    token_key = make_key()
    call_command("createtoken", "foo@example.com", token_key, stdout=stdout)

    assert Token.objects.filter(key=token_key).count() == 1


@pytest.mark.django_db
def test_createtoken_command_no_user():
    with pytest.raises(CommandError):
        stdout = StringIO()
        call_command("createtoken", "foo@example.com", stdout=stdout)


@pytest.mark.django_db
def test_client_homepage_with_valid_token(client):
    url = reverse("api:auth")
    response = client.get(url)
    assert response.status_code == 200
    assert "sign_in_url" in response.json()

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    assert not user.last_login
    token = Token.objects.create(user=user)
    token_key = token.key

    response = client.get(url, HTTP_AUTH_TOKEN=token_key)
    assert response.status_code == 200
    assert "sign_in_url" not in response.json()["user"]
    assert response.json()["user"]["email"] == user.email
    assert response.headers.get("Vary").lower() == "auth-token"
    user.refresh_from_db()
    assert user.last_login

    # Test with token comment
    token_key = f"{token_key}-testtoken"
    response = client.get(url, HTTP_AUTH_TOKEN=token_key)
    assert response.status_code == 200
    assert "sign_in_url" not in response.json()["user"]
    assert response.json()["user"]["email"] == user.email
    assert response.headers.get("Vary").lower() == "auth-token"
    user.refresh_from_db()
    assert user.last_login


@pytest.mark.django_db
def test_client_homepage_with_invalid_token(client):
    url = reverse("api:auth")
    response = client.get(url, HTTP_AUTH_TOKEN="junk")
    assert response.status_code == 403
    assert b"API Token not matched" in response.content

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    token = Token.objects.create(user=user)
    token.expires_at = timezone.now()
    token.save()

    response = client.get(url, HTTP_AUTH_TOKEN=token.key)
    assert response.status_code == 403
    assert b"API Token found but expired" in response.content

    token.expires_at += datetime.timedelta(days=1)
    token.save()
    # but now mess with the user
    user.is_active = False
    user.save()

    response = client.get(url, HTTP_AUTH_TOKEN=token.key)
    assert response.status_code == 403
    assert b"API Token matched but user not active" in response.content


@pytest.mark.django_db
def test_token_permission_signal():
    content_type = ContentType.objects.get(app_label="tokens")
    permission = Permission.objects.create(
        name="Do", content_type=content_type, codename="do"
    )
    other_permission = Permission.objects.create(
        name="Do Not", content_type=content_type, codename="donot"
    )

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    token = Token.objects.create(user=user)
    token.permissions.add(permission)
    token.permissions.add(other_permission)

    users = Group.objects.create(name="Users")
    user.groups.add(users)
    users.permissions.add(permission)
    users.permissions.add(other_permission)

    assert token.permissions.all().count() == 2

    # Delete one permission from the group
    users.permissions.remove(other_permission)
    assert token.permissions.all().count() == 1
    assert list(token.permissions.all()) == [permission]
