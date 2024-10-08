# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime
from unittest.mock import ANY

import pytest

from django.contrib.auth.models import User, Permission
from django.urls import reverse
from django.utils import timezone

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload
from tecken.api.views import filter_uploads
from tecken.api.forms import UploadsForm, BaseFilteringForm


@pytest.mark.django_db
def test_auth(client):
    url = reverse("api:auth")
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert not data.get("user")
    assert data["sign_in_url"]

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["is_active"]
    assert not data["user"]["is_superuser"]
    assert data["user"]["email"]
    assert data["sign_out_url"]
    assert not data["user"]["permissions"]

    permission = Permission.objects.get(codename="manage_tokens")
    user.user_permissions.add(permission)
    permission = Permission.objects.get(codename="upload_symbols")
    user.user_permissions.add(permission)

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert "upload.upload_symbols" in [
        x["codename"] for x in data["user"]["permissions"]
    ]
    assert "tokens.manage_tokens" in [
        x["codename"] for x in data["user"]["permissions"]
    ]


@pytest.mark.django_db
def test_tokens(client):
    url = reverse("api:tokens")
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.get(url)
    assert response.status_code == 403

    permission = Permission.objects.get(codename="manage_tokens")
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["tokens"] == []
    assert data["permissions"] == []

    # Let's try again, but this time give the user some permissions
    # and existing tokens.

    permission = Permission.objects.get(codename="upload_symbols")
    user.user_permissions.add(permission)

    token = Token.objects.create(user=user, notes="hej!")
    token.permissions.add(permission)

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()

    (dt,) = data["tokens"]
    assert dt["id"] == token.id
    assert dt["key"] == token.key
    assert dt["notes"] == token.notes
    assert not dt["is_expired"] == token.key
    # Can't just compare with .isoformat() since DjangoJSONEncoder
    # does special things with the timezone
    assert dt["expires_at"][:20] == token.expires_at.isoformat()[:20]
    assert dt["permissions"] == [{"id": permission.id, "name": permission.name}]

    assert data["permissions"] == [{"id": permission.id, "name": permission.name}]


@pytest.mark.django_db
def test_tokens_filtering(client):
    url = reverse("api:tokens")
    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")
    permission = Permission.objects.get(codename="manage_tokens")
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["tokens"] == []
    assert data["totals"] == {"active": 0, "all": 0, "expired": 0}

    # Create 2 tokens. One expired and one not expired.
    t1 = Token.objects.create(user=user, notes="current")
    assert not t1.is_expired
    yesterday = timezone.now() - datetime.timedelta(days=1)
    t2 = Token.objects.create(user=user, expires_at=yesterday, notes="gone")
    assert t2.is_expired

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert len(data["tokens"]) == 1
    assert [x["notes"] for x in data["tokens"]] == ["current"]
    assert data["totals"] == {"active": 1, "all": 2, "expired": 1}

    # Filter on the expired ones
    response = client.get(url, {"state": "expired"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["tokens"]) == 1
    assert [x["notes"] for x in data["tokens"]] == ["gone"]

    # Filter on 'all'
    response = client.get(url, {"state": "all"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["tokens"]) == 2
    assert [x["notes"] for x in data["tokens"]] == ["gone", "current"]

    # Filter incorrectly
    response = client.get(url, {"state": "junks"})
    assert response.status_code == 400


@pytest.mark.django_db
def test_tokens_create(client):
    url = reverse("api:tokens")
    response = client.post(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    permission = Permission.objects.get(codename="manage_tokens")
    user.user_permissions.add(permission)
    assert client.login(username="peterbe", password="secret")

    response = client.post(url)
    assert response.status_code == 400
    assert response.json()["errors"]["permissions"]
    assert response.json()["errors"]["expires"]

    permission = Permission.objects.get(codename="upload_symbols")
    user.user_permissions.add(permission)
    response = client.post(
        url, {"permissions": f"{permission.id}", "expires": "notaninteger"}
    )
    assert response.status_code == 400
    assert response.json()["errors"]["expires"]

    not_your_permission = Permission.objects.get(codename="view_all_uploads")
    response = client.post(
        url, {"permissions": f"{not_your_permission.id}", "expires": "10"}
    )
    assert response.status_code == 403
    assert response.json()["error"] == (
        "View All Symbols Uploads not a valid permission"
    )

    response = client.post(
        url, {"permissions": f"{permission.id}", "expires": "10", "notes": "Hey man!  "}
    )
    assert response.status_code == 201
    token = Token.objects.get(notes="Hey man!")
    future = token.expires_at - timezone.now()
    # due to rounding, we can't compare the seconds as equals
    epsilon = abs(future.total_seconds() - 10 * 24 * 60 * 60)
    assert epsilon < 1
    assert permission in token.permissions.all()


@pytest.mark.django_db
def test_tokens_create_bad_permissions_combo(client):
    url = reverse("api:tokens")
    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    permission0 = Permission.objects.get(codename="manage_tokens")
    user.user_permissions.add(permission0)
    permission1 = Permission.objects.get(codename="upload_try_symbols")
    user.user_permissions.add(permission1)
    permission2 = Permission.objects.get(codename="upload_symbols")
    user.user_permissions.add(permission2)
    assert client.login(username="peterbe", password="secret")

    response = client.post(
        url, {"permissions": f"{permission1.id},{permission2.id}", "expires": "10"}
    )
    assert response.status_code == 400
    errors = response.json()["errors"]
    assert errors == {"permissions": ["Invalid combination of permissions"]}


@pytest.mark.django_db
def test_tokens_delete(client):
    url = reverse("api:delete_token", args=(9_999_999,))
    response = client.post(url)
    assert response.status_code == 405

    response = client.delete(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.delete(url)
    assert response.status_code == 404

    # Create an actual token that can be deleted
    token = Token.objects.create(user=user)
    url = reverse("api:delete_token", args=(token.id,))
    response = client.delete(url)
    assert response.status_code == 200
    assert not Token.objects.filter(user=user)

    # Try to delete someone else's token and it should fail
    other_user = User.objects.create(username="other")
    token = Token.objects.create(user=other_user)
    url = reverse("api:delete_token", args=(token.id,))
    response = client.delete(url)
    assert response.status_code == 404

    # ...but works if you're a superuser
    user.is_superuser = True
    user.save()
    response = client.delete(url)
    assert response.status_code == 200
    assert not Token.objects.filter(user=other_user)


@pytest.mark.django_db
def test_tokens_extend(client):
    url = reverse("api:extend_token", args=(9_999_999,))
    response = client.get(url)
    assert response.status_code == 405

    response = client.post(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.post(url)
    assert response.status_code == 404

    # Create an actual token that can be deleted
    token = Token.objects.create(user=user)
    url = reverse("api:extend_token", args=(token.id,))
    response = client.post(url, {"days": "xxx"})
    assert response.status_code == 400
    response = client.post(url, {"days": "10"})
    assert response.status_code == 200
    expires_before = token.expires_at
    token.refresh_from_db()
    expires_after = token.expires_at
    assert (expires_after - expires_before).days == 10


def test_form_order_by():
    """Any form that inherits BaseFilteringForm has the ability to
    set 'sort' and 'reverse' and when cleaned returns a dict called
    'order_by'"""
    form = BaseFilteringForm({})
    assert form.is_valid()
    assert not form.cleaned_data.get("order_by")
    form = BaseFilteringForm({"sort": "foo", "reverse": "true"})
    assert form.is_valid()
    assert form.cleaned_data["order_by"] == {"sort": "foo", "reverse": True}
    form = BaseFilteringForm(
        {"sort": "foo", "reverse": "true"}, valid_sorts=("key1", "key2")
    )
    assert not form.is_valid()
    assert form.errors["sort"]


def test_uploadsform_dates():
    form = UploadsForm({"created_at": ""})
    assert form.is_valid()
    assert form.cleaned_data["created_at"] == []

    form = UploadsForm({"created_at": "2017-07-28"})
    assert form.is_valid()
    operator, value = form.cleaned_data["created_at"][0]
    assert operator == "="
    assert isinstance(value, datetime.datetime)
    assert value.tzinfo

    form = UploadsForm({"created_at": ">= 2017-07-28"})
    assert form.is_valid()
    operator, value = form.cleaned_data["created_at"][0]
    assert operator == ">="

    form = UploadsForm({"created_at": "<2017-07-26T14:01:41.956Z"})
    assert form.is_valid()
    operator, value = form.cleaned_data["created_at"][0]
    assert operator == "<"
    assert isinstance(value, datetime.datetime)
    assert value.tzinfo
    assert value.hour == 14

    form = UploadsForm({"created_at": "= null"})
    assert form.is_valid()
    operator, value = form.cleaned_data["created_at"][0]
    assert operator == "="
    assert value is None

    form = UploadsForm({"created_at": "Incomplete"})
    assert form.is_valid()
    operator, value = form.cleaned_data["created_at"][0]
    assert operator == "="
    assert value is None

    # Now pass in some junk
    form = UploadsForm({"created_at": "2017-88-28"})
    assert not form.is_valid()
    form = UploadsForm({"created_at": "%2017-01-23"})
    assert not form.is_valid()

    form = UploadsForm({"created_at": "Today"})
    assert form.is_valid()
    operator, value = form.cleaned_data["created_at"][0]
    assert operator == "="
    now = timezone.now()
    assert value.strftime("%Y%m%d") == now.strftime("%Y%m%d")

    form = UploadsForm({"created_at": "yesterDAY"})
    assert form.is_valid()
    operator, value = form.cleaned_data["created_at"][0]
    assert operator == "="
    yesterday = now - datetime.timedelta(days=1)
    assert value.strftime("%Y%m%d") == yesterday.strftime("%Y%m%d")


def test_uploadsform_size():
    form = UploadsForm({"size": ""})
    assert form.is_valid()
    assert form.cleaned_data["size"] == []

    form = UploadsForm({"size": "1234"})
    assert form.is_valid()
    operator, value = form.cleaned_data["size"][0]
    assert operator == "="
    assert value == 1234

    form = UploadsForm({"size": ">=10MB"})
    assert form.is_valid()
    operator, value = form.cleaned_data["size"][0]
    assert operator == ">="
    assert value == 10 * 1024 * 1024


@pytest.mark.django_db
def test_uploadsform_user():
    form = UploadsForm({"user": "peterbe"})
    # Valid even though there is no user with that email.
    assert form.is_valid()
    assert form.cleaned_data["user"][0] == "="
    assert form.cleaned_data["user"][1] == "peterbe"

    # Negate now, when there is still no matching user.
    form = UploadsForm({"user": "!peterbe"})
    # Valid even though there is no user with that email.
    assert form.is_valid()
    assert form.cleaned_data["user"][0] == "!"
    assert form.cleaned_data["user"][1] == "peterbe"

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    form = UploadsForm({"user": "peterbe"})
    assert form.is_valid()
    assert form.cleaned_data["user"][0] == "="
    assert form.cleaned_data["user"][1] == user

    # Negate
    form = UploadsForm({"user": "!peterbe"})
    assert form.is_valid()
    assert form.cleaned_data["user"][0] == "!"
    assert form.cleaned_data["user"][1] == user

    # What if there are more than 1 user that matches.
    user = User.objects.create(username="p", email="example@peterbe.com")
    form = UploadsForm({"user": "peterbe"})
    assert form.is_valid()
    assert form.cleaned_data["user"][0] == "="
    assert form.cleaned_data["user"][1] == "peterbe"


@pytest.mark.django_db
def test_uploads(client):
    url = reverse("api:uploads")
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"] == []
    assert not data["can_view_all"]

    # Don't mess with the 'page' key
    response = client.get(url, {"page": "notanumber"})
    assert response.status_code == 400
    # If you make it 0 or less, it just sends you to page 1
    response = client.get(url, {"page": "0"})
    assert response.status_code == 200

    # Let's pretend there's an upload belonging to someone else
    upload = Upload.objects.create(
        user=User.objects.create(email="her@example.com"), size=123_456
    )
    # Confidence check
    assert upload.created_at
    assert not upload.completed_at

    # Also, let's pretend there's at least one file upload
    FileUpload.objects.create(upload=upload, size=1234, key="foo.sym")

    # Even if there is an upload, because you don't have permission
    # yet, it should not show up.
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"] == []

    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"][0]["id"] == upload.id
    assert data["uploads"][0]["user"] == {"email": "her@example.com"}
    assert data["uploads"][0]["files_count"] == 0
    assert data["uploads"][0]["files_incomplete_count"] == 1
    assert data["can_view_all"]

    # Now you can search for anybody's uploads
    response = client.get(url, {"user": "HER@"})
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"][0]["id"] == upload.id

    User.objects.create(email="nother@example.com", username="nother")
    # Now this becomes ambiguous
    response = client.get(url, {"user": "her@"})
    assert response.status_code == 200
    assert data["uploads"][0]["id"] == upload.id
    # Be specific this time.
    response = client.get(url, {"user": "her@example.com"})
    assert response.status_code == 200
    assert data["uploads"][0]["id"] == upload.id
    # Anybody elses uploads
    response = client.get(url, {"user": "! her@example.com"})
    assert response.status_code == 200
    assert not response.json()["uploads"]  # expect it to be empty

    # Filter incorrectly
    response = client.get(url, {"size": ">= xxx"})
    assert response.status_code == 400
    assert response.json()["errors"]["size"]

    # Filter incorrectly
    response = client.get(url, {"size": "mozilla.com"})
    assert response.status_code == 400
    assert response.json()["errors"]["size"]

    # Let's filter on size
    response = client.get(url, {"size": ">= 10KB"})
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"][0]["id"] == upload.id
    response = client.get(url, {"size": "< 1000"})
    assert response.status_code == 200
    data = response.json()
    assert not data["uploads"]
    # Filter on "multiple sizes"
    response = client.get(url, {"size": ">= 10KB, < 1g"})
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"][0]["id"] == upload.id

    # Let's filter on dates
    response = client.get(
        url,
        {
            "created_at": ">" + upload.created_at.date().strftime("%Y-%m-%d"),
            "completed_at": "Incomplete",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"][0]["id"] == upload.id
    # Filter on a specific *day* is exceptional
    response = client.get(
        url, {"created_at": upload.created_at.date().strftime("%Y-%m-%d")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"][0]["id"] == upload.id
    day_before = upload.created_at - datetime.timedelta(days=1)
    response = client.get(url, {"created_at": day_before.strftime("%Y-%m-%d")})
    assert response.status_code == 200
    data = response.json()
    assert not data["uploads"]


@pytest.mark.django_db
def test_uploads_count(client):
    url = reverse("api:uploads")
    user = User.objects.create(username="user1", email="user1@example.com")
    user.set_password("secret")
    user.save()
    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)
    assert client.login(username="user1", password="secret")

    # Create upload
    upload = Upload.objects.create(
        user=User.objects.create(email="user2@example.com"), size=123_456
    )
    FileUpload.objects.create(upload=upload, size=1234, key="foo.sym")

    # Fetch uploads with no filters
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"] == [
        {
            "bucket_name": "",
            "completed_at": None,
            "created_at": ANY,
            "download_url": None,
            "filename": "",
            "files_count": 0,
            "files_incomplete_count": 1,
            "id": 2,
            "ignored_keys": [],
            "redirect_urls": [],
            "size": 123456,
            "skipped_keys": [],
            "try_symbols": False,
            "user": {"email": "user2@example.com"},
        },
    ]

    # No filters results in total being magic big "I didn't count this" number of
    # 1,000,000
    assert data["total"] == 1000000

    # Fetch uploads with size
    response = client.get(url, {"size": ">= 10KB"})
    assert response.status_code == 200
    data = response.json()
    assert data["uploads"] == [
        {
            "bucket_name": "",
            "completed_at": None,
            "created_at": ANY,
            "download_url": None,
            "filename": "",
            "files_count": 0,
            "files_incomplete_count": 1,
            "id": 2,
            "ignored_keys": [],
            "redirect_urls": [],
            "size": 123456,
            "skipped_keys": [],
            "try_symbols": False,
            "user": {"email": "user2@example.com"},
        },
    ]
    assert data["total"] == 1


@pytest.mark.django_db
def test_uploads_second_increment(client):
    """If you query uploads with '?created_at=>SOMEDATE' that date
    gets an extra second added to it. That's because the datetime objects
    are stored in the ORM with microseconds but in JSON dumps (isoformat())
    the date loses that accuracy and if you take the lates upload's
    'created_at' and use the '>' operator it shouldn't be included."""
    url = reverse("api:uploads")
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)
    assert client.login(username="peterbe", password="secret")

    Upload.objects.create(
        user=User.objects.create(email="her@example.com"), size=123_456
    )

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    # NOTE(willkg): This is the magic big number
    assert data["total"] == 1000000

    last_created_at = data["uploads"][0]["created_at"]
    response = client.get(url, {"created_at": f">{last_created_at}"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0

    # But if you use '>=' operator it should be fine and it should be included.
    response = client.get(url, {"created_at": f">={last_created_at}"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1


@pytest.mark.django_db
def test_upload(client):
    url = reverse("api:upload", args=(9_999_999,))
    response = client.get(url)
    # Won't even let you in to find out that ID doesn't exist.
    assert response.status_code == 403

    # What if you're signed in
    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.get(url)
    # Won't even let you in to find out that ID doesn't exist.
    assert response.status_code == 404

    upload = Upload.objects.create(
        user=User.objects.create(email="her@example.com"),
        size=123_456,
        skipped_keys=["foo"],
        ignored_keys=["bar"],
    )
    FileUpload.objects.create(upload=upload, size=1234, key="foo.sym")
    url = reverse("api:upload", args=(upload.id,))
    response = client.get(url)
    # You can't view it because you don't have access to it.
    assert response.status_code == 403

    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200

    result = response.json()
    assert result["upload"]["id"] == upload.id
    assert result["upload"]["user"]["email"] == upload.user.email
    assert result["upload"]["related"] == []
    (first_file_upload,) = result["upload"]["file_uploads"]
    assert first_file_upload["size"] == 1234


@pytest.mark.django_db
def test_upload_related(client):
    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)
    assert client.login(username="peterbe", password="secret")

    upload = Upload.objects.create(
        user=User.objects.create(email="her@example.com"),
        size=123_456,
        skipped_keys=["foo"],
        ignored_keys=["bar"],
        filename="symbols.zip",
    )
    FileUpload.objects.create(upload=upload, size=1234, key="foo.sym")

    upload2 = Upload.objects.create(
        user=upload.user, size=upload.size, filename=upload.filename
    )

    url = reverse("api:upload", args=(upload.id,))
    response = client.get(url)
    assert response.status_code == 200
    result = response.json()
    assert result["upload"]["related"][0]["id"] == upload2.id

    upload3 = Upload.objects.create(
        user=upload.user,
        size=upload.size,
        filename="different.zip",
        content_hash="deadbeef123",
    )
    upload.content_hash = upload3.content_hash
    upload.save()
    response = client.get(url)
    assert response.status_code == 200
    result = response.json()
    assert result["upload"]["related"][0]["id"] == upload3.id


@pytest.mark.django_db
def test_upload_files(client, settings):
    url = reverse("api:upload_files")
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username="user1", email="user1@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="user1", password="secret")

    response = client.get(url)
    assert response.status_code == 403

    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["files"] == []

    # Don't mess with the 'page' key
    error_body = {"errors": {"page": ["Not a number 'notanumber'"]}}
    response = client.get(url, {"page": "notanumber"})
    assert response.status_code == 400
    assert response.json() == error_body

    # Let's pretend there's an upload belonging to someone else
    upload = Upload.objects.create(
        user=User.objects.create(email="user2@example.com"), size=123_456
    )
    # Confidence check
    assert upload.created_at
    assert not upload.completed_at
    # Also, let's pretend there's at least one file upload
    file_upload1 = FileUpload.objects.create(
        upload=upload,
        size=1234,
        bucket_name="other-public",
        key="v1/bar.pdb/46A0ADB3F299A70B4C4C44205044422E1/bar.sym",
    )
    file_upload2 = FileUpload.objects.create(
        size=100,
        bucket_name="symbols-public",
        key="v1/libxul.so/A772CC9A3E852CF48965ED79FB65E3150/libxul.so.sym",
        compressed=True,
    )

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["files"]
    all_ids = {file_upload1.id, file_upload2.id}
    assert {x["id"] for x in data["files"]} == all_ids
    assert data["batch_size"] == settings.API_FILES_BATCH_SIZE

    # No filters yields BIG_NUMBER total
    assert data["total"] == 1000000

    # Check the 'upload' which should either be None or a dict
    for file_upload in data["files"]:
        if file_upload["id"] == file_upload1.id:
            assert file_upload["upload"]["id"] == upload.id
            assert file_upload["upload"]["user"]["id"] == upload.user.id
            assert file_upload["upload"]["created_at"]
        else:
            assert file_upload["upload"] is None

    # Filter by created_at and completed_at
    response = client.get(
        url,
        {
            "created_at": ">" + upload.created_at.date().strftime("%Y-%m-%d"),
            "completed_at": "Incomplete",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert {x["id"] for x in data["files"]} == all_ids

    tomorrow = file_upload1.created_at + datetime.timedelta(days=1)
    file_upload1.completed_at = tomorrow
    file_upload1.save()
    response = client.get(url, {"completed_at": tomorrow.strftime("%Y-%m-%d")})
    assert response.status_code == 200
    data = response.json()
    assert [x["id"] for x in data["files"]] == [file_upload1.id]

    # Let's filter on size
    response = client.get(url, {"size": ">= 1KB"})
    assert response.status_code == 200
    data = response.json()
    assert [x["id"] for x in data["files"]] == [file_upload1.id]

    # Filter by key
    response = client.get(url, {"key": "sym"})
    assert response.status_code == 200
    data = response.json()
    assert {x["id"] for x in data["files"]} == all_ids
    response = client.get(
        url, {"key": "libxul.so.sym, A772CC9A3E852CF48965ED79FB65E3150"}
    )
    assert response.status_code == 200
    data = response.json()
    assert [x["id"] for x in data["files"]] == [file_upload2.id]

    # Filter by bucket_name
    response = client.get(url, {"bucket_name": file_upload1.bucket_name})
    assert response.status_code == 200
    data = response.json()
    assert [x["id"] for x in data["files"]] == [file_upload1.id]

    # By negated bucket name
    response = client.get(url, {"bucket_name": f"!{file_upload1.bucket_name}"})
    assert response.status_code == 200
    data = response.json()
    assert [x["id"] for x in data["files"]] == [file_upload2.id]


@pytest.mark.django_db
def test_upload_files_filter_upload_type(client, settings):
    url = reverse("api:upload_files")

    user = User.objects.create(username="user1", email="user1@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="user1", password="secret")

    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)

    # Create upload data
    regular_upload = Upload.objects.create(user=user, size=123_456)
    regular_file = FileUpload.objects.create(
        upload=regular_upload,
        size=1234,
        bucket_name="symbols-public",
        key="bar.pdb/46A0ADB3F299A70B4C4C44205044422E1/bar.sym",
    )

    try_upload = Upload.objects.create(user=user, size=123_456, try_symbols=True)
    try_file = FileUpload.objects.create(
        upload=try_upload,
        size=100,
        bucket_name="symbols-public",
        key="v1/libxul.so/A772CC9A3E852CF48965ED79FB65E3150/libxul.so.sym",
    )

    # Request all files--should return both files
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["files"]
    all_ids = {regular_file.id, try_file.id}
    assert {x["id"] for x in data["files"]} == all_ids

    # Request upload_type=""--should return both files
    response = client.get(url, {"upload_type": ""})
    assert response.status_code == 200
    data = response.json()
    assert {x["id"] for x in data["files"]} == all_ids

    # Request upload_type="try"--should return only try file
    response = client.get(url, {"upload_type": "try"})
    assert response.status_code == 200
    data = response.json()
    assert {x["id"] for x in data["files"]} == {try_file.id}

    # Request upload_type="regular"--should return only regular file
    response = client.get(url, {"upload_type": "regular"})
    assert response.status_code == 200
    data = response.json()
    assert {x["id"] for x in data["files"]} == {regular_file.id}


@pytest.mark.django_db
def test_upload_files_count(client):
    url = reverse("api:upload_files")
    user = User.objects.create(username="user1", email="user1@example.com")
    user.set_password("secret")
    user.save()
    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)
    assert client.login(username="user1", password="secret")

    # Create data
    regular_upload = Upload.objects.create(user=user, size=123_456)
    regular_file_upload = FileUpload.objects.create(
        upload=regular_upload,
        size=1234,
        bucket_name="symbols-public",
        key="bar.pdb/46A0ADB3F299A70B4C4C44205044422E1/bar.sym",
    )

    try_upload = Upload.objects.create(user=user, size=123_456, try_symbols=True)
    try_file_upload = FileUpload.objects.create(
        upload=try_upload,
        size=50,
        bucket_name="symbols-public",
        key="libxul.so/9B6C6BD630483C5F453471EE0EEEB09A0/libxul.so.sym",
    )

    file_upload = FileUpload.objects.create(
        size=100,
        bucket_name="symbols-public",
        key="libxul.so/A772CC9A3E852CF48965ED79FB65E3150/libxul.so.sym",
        compressed=True,
    )

    # Fetch uploads with no filters
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["files"] == [
        {
            "id": file_upload.id,
            "key": "libxul.so/A772CC9A3E852CF48965ED79FB65E3150/libxul.so.sym",
            "update": False,
            "compressed": True,
            "size": 100,
            "bucket_name": "symbols-public",
            "completed_at": None,
            "created_at": ANY,
            "upload": None,
        },
        {
            "bucket_name": "symbols-public",
            "completed_at": None,
            "compressed": False,
            "created_at": ANY,
            "id": try_file_upload.id,
            "key": "libxul.so/9B6C6BD630483C5F453471EE0EEEB09A0/libxul.so.sym",
            "size": 50,
            "update": False,
            "upload": {
                "created_at": ANY,
                "id": try_upload.id,
                "try_symbols": True,
                "upload_type": "try",
                "user": {"id": user.id, "email": "user1@example.com"},
            },
        },
        {
            "id": regular_file_upload.id,
            "key": "bar.pdb/46A0ADB3F299A70B4C4C44205044422E1/bar.sym",
            "update": False,
            "compressed": False,
            "size": 1234,
            "bucket_name": "symbols-public",
            "completed_at": None,
            "created_at": ANY,
            "upload": {
                "id": regular_upload.id,
                "try_symbols": False,
                "upload_type": "regular",
                "user": {"id": user.id, "email": "user1@example.com"},
                "created_at": ANY,
            },
        },
    ]

    # No filters results in total being magic big "I didn't count this" number of
    # 1,000,000
    assert data["total"] == 1000000

    # Fetch uploads with size
    response = client.get(url, {"size": "> 100"})
    assert response.status_code == 200
    data = response.json()
    assert data["files"] == [
        {
            "bucket_name": "symbols-public",
            "completed_at": None,
            "compressed": False,
            "created_at": ANY,
            "id": regular_file_upload.id,
            "key": "bar.pdb/46A0ADB3F299A70B4C4C44205044422E1/bar.sym",
            "size": 1234,
            "update": False,
            "upload": {
                "created_at": ANY,
                "id": regular_upload.id,
                "try_symbols": False,
                "upload_type": "regular",
                "user": {
                    "email": "user1@example.com",
                    "id": user.id,
                },
            },
        },
    ]
    assert data["total"] == 1


@pytest.mark.django_db
def test_stats(client):
    url = reverse("api:stats")
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["stats"] == {
        "uploads": {
            # NOTE: all_uploads == False
            "all_uploads": False,
            "today": {"count": 0, "total_size": 0},
            "yesterday": {"count": 0, "total_size": 0},
            "last_30_days": {"count": 0, "total_size": 0},
        },
    }

    user.is_superuser = True
    user.save()

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["stats"] == {
        "uploads": {
            # NOTE: all_uploads == True
            "all_uploads": True,
            "today": {"count": 0, "total_size": 0},
            "yesterday": {"count": 0, "total_size": 0},
            "last_30_days": {"count": 0, "total_size": 0},
        },
    }


@pytest.mark.django_db
def test_filter_uploads_by_size():
    """Test the utility function filter_uploads()"""
    user1 = User.objects.create(email="test@example.com")
    Upload.objects.create(user=user1, filename="symbols1.zip", size=1234)
    form = UploadsForm({})
    assert form.is_valid()
    qs = Upload.objects.all()
    assert filter_uploads(qs, True, user1, form).count() == 1

    form = UploadsForm({"size": ">1234"})
    assert form.is_valid()
    assert filter_uploads(qs, True, user1, form).count() == 0

    form = UploadsForm({"size": ">=1234"})
    assert form.is_valid()
    assert filter_uploads(qs, True, user1, form).count() == 1

    form = UploadsForm({"size": ">1Kb"})
    assert form.is_valid()
    assert filter_uploads(qs, True, user1, form).count() == 1


@pytest.mark.django_db
def test_filter_uploads_by_user():
    """Test the utility function filter_uploads()"""
    user1 = User.objects.create(username="test1")
    Upload.objects.create(user=user1, filename="symbols1.zip", size=1234)
    user2 = User.objects.create(username="test2")
    Upload.objects.create(user=user2, filename="symbols2.zip", size=123_456_789)
    qs = Upload.objects.all()
    form = UploadsForm({})
    assert form.is_valid()
    assert filter_uploads(qs, False, user1, form).count() == 1
    assert filter_uploads(qs, True, user1, form).count() == 2

    user3 = User.objects.create(username="test3")
    assert filter_uploads(qs, True, user1, form).count() == 2
    assert filter_uploads(qs, False, user3, form).count() == 0


@pytest.mark.django_db
def test_filter_uploads_by_completed_at():
    """Test the utility function filter_uploads()"""
    user1 = User.objects.create(username="test1")
    Upload.objects.create(user=user1, filename="symbols1.zip", size=1234)
    Upload.objects.create(
        user=user1, filename="symbols2.zip", size=1234, completed_at=timezone.now()
    )
    qs = Upload.objects.all()

    form = UploadsForm({"completed_at": "Incomplete"})
    assert form.is_valid()
    assert filter_uploads(qs, True, user1, form).count() == 1

    form = UploadsForm({"completed_at": "today"})
    assert form.is_valid()
    assert filter_uploads(qs, True, user1, form).count() == 1

    form = UploadsForm({"completed_at": "<2017-10-09"})
    assert form.is_valid()
    assert filter_uploads(qs, True, user1, form).count() == 0

    today = timezone.now()
    form = UploadsForm({"completed_at": today.strftime("%Y-%m-%d")})
    assert form.is_valid()
    assert filter_uploads(qs, True, user1, form).count() == 1

    form = UploadsForm({"completed_at": ">" + today.isoformat()})
    assert form.is_valid()
    assert filter_uploads(qs, True, user1, form).count() == 0


@pytest.mark.django_db
def test_file_upload(client):
    url = reverse("api:upload_file", args=("9999999999",))
    response = client.get(url)
    # Forbidden before Not Found
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.get(url)
    # Now, you get a 404
    assert response.status_code == 404

    upload = Upload.objects.create(
        user=User.objects.create(email="her@example.com"), size=123_456
    )
    # Also, let's pretend there's at least one file upload
    file_upload = FileUpload.objects.create(
        upload=upload,
        size=1234,
        bucket_name="other-public",
        key="v1/bar.pdb/46A0ADB3F299A70B4C4C44205044422E1/bar.sym",
        debug_filename="bar.pdb",
        debug_id="46A0ADB3F299A70B4C4C44205044422E1",
        code_file="bar.dll",
        code_id="64EC878F867C000",
        generator="mozilla/dump_syms XYZ",
    )
    url = reverse("api:upload_file", args=(file_upload.id,))
    response = client.get(url)
    # 403 because it's not your file to view
    assert response.status_code == 403

    # Pretend it was you who uploaded it
    upload.user = user
    upload.save()
    response = client.get(url)
    assert response.status_code == 200

    data = response.json()["file"]
    assert data["upload"]["user"]["email"] == user.email
    assert data["url"] == "/bar.pdb/46A0ADB3F299A70B4C4C44205044422E1/bar.sym"
    assert list(sorted(data.keys())) == [
        "bucket_name",
        "code_file",
        "code_id",
        "completed_at",
        "compressed",
        "created_at",
        "debug_filename",
        "debug_id",
        "generator",
        "id",
        "key",
        "size",
        "update",
        "upload",
        "url",
    ]


@pytest.mark.django_db
def test_file_upload_try_upload(client):
    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    upload = Upload.objects.create(user=user, size=123_456, try_symbols=True)
    # Also, let's pretend there's at least one file upload
    file_upload = FileUpload.objects.create(
        upload=upload, size=1234, key="foo.pdb/deadbeaf123/foo.sym"
    )
    url = reverse("api:upload_file", args=(file_upload.id,))
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "file": {
            "bucket_name": "",
            "code_file": None,
            "code_id": None,
            "completed_at": None,
            "compressed": False,
            "created_at": ANY,
            "debug_filename": None,
            "debug_id": None,
            "generator": None,
            "id": file_upload.id,
            "key": "foo.pdb/deadbeaf123/foo.sym",
            "size": 1234,
            "update": False,
            "upload": {
                "bucket_name": "",
                "completed_at": None,
                "created_at": ANY,
                "download_url": None,
                "filename": "",
                "id": upload.id,
                "ignored_keys": [],
                "redirect_urls": [],
                "size": 123_456,
                "skipped_keys": [],
                "try_symbols": True,
                "user": {
                    "email": "peterbe@example.com",
                    "id": user.id,
                },
            },
            "url": "/foo.pdb/deadbeaf123/foo.sym?try",
        }
    }


class Test_syminfo:
    def test_debuginfo_lookup(self, client, db, metricsmock):
        sym_file = "xul.sym"
        debug_filename = "xul.pdb"
        debug_id = "404B9729BE96C3CF4C4C44205044422E1"
        code_file = "xul.dll"
        code_id = "64E130A115A30000"
        generator = "mozilla/dump_syms XYZ"

        FileUpload.objects.create(
            bucket_name="publicbucket",
            key=f"v1/{debug_filename}/{debug_id}/{sym_file}",
            size=100,
            debug_filename=debug_filename,
            debug_id=debug_id,
            code_file=code_file,
            code_id=code_id,
            generator=generator,
        )

        # Try syminfo with debug info
        url = reverse("api:syminfo", args=(debug_filename, debug_id))
        response = client.get(url)
        assert response.status_code == 200
        assert response.json() == {
            "debug_filename": debug_filename,
            "debug_id": debug_id,
            "code_file": code_file,
            "code_id": code_id,
            "generator": generator,
            "url": f"http://testserver/{debug_filename}/{debug_id}/{sym_file}",
        }
        metricsmock.assert_timing(
            "tecken.syminfo.lookup.timing", tags=["host:testnode"]
        )
        metricsmock.assert_incr(
            "tecken.syminfo.lookup.cached", tags=["result:false", "host:testnode"]
        )

    def test_codeinfo_lookup(self, client, db, metricsmock):
        sym_file = "xul.sym"
        debug_filename = "xul.pdb"
        debug_id = "404B9729BE96C3CF4C4C44205044422E1"
        code_file = "xul.dll"
        code_id = "64E130A115A30000"
        generator = "mozilla/dump_syms XYZ"

        FileUpload.objects.create(
            bucket_name="publicbucket",
            key=f"v1/{debug_filename}/{debug_id}/{sym_file}",
            size=100,
            debug_filename=debug_filename,
            debug_id=debug_id,
            code_file=code_file,
            code_id=code_id,
            generator=generator,
        )

        # Try syminfo with debug info
        url = reverse("api:syminfo", args=(code_file, code_id))
        response = client.get(url)
        assert response.status_code == 200
        assert response.json() == {
            "debug_filename": debug_filename,
            "debug_id": debug_id,
            "code_file": code_file,
            "code_id": code_id,
            "generator": generator,
            "url": f"http://testserver/{debug_filename}/{debug_id}/{sym_file}",
        }
        metricsmock.assert_timing(
            "tecken.syminfo.lookup.timing", tags=["host:testnode"]
        )
        metricsmock.assert_incr(
            "tecken.syminfo.lookup.cached", tags=["result:false", "host:testnode"]
        )

    def test_try_lookup(self, client, db, metricsmock):
        sym_file = "xul.sym"
        debug_filename = "xul.pdb"
        debug_id = "404B9729BE96C3CF4C4C44205044422E1"
        code_file = "xul.dll"
        code_id = "64E130A115A30000"
        generator = "mozilla/dump_syms XYZ"

        upload = Upload.objects.create(
            user=User.objects.create(email="user2@example.com"),
            size=123_456,
            try_symbols=True,
        )
        FileUpload.objects.create(
            bucket_name="publicbucket",
            key=f"try/v1/{debug_filename}/{debug_id}/{sym_file}",
            size=100,
            debug_filename=debug_filename,
            debug_id=debug_id,
            code_file=code_file,
            code_id=code_id,
            generator=generator,
            upload=upload,
        )

        # Try syminfo with debug info
        url = reverse("api:syminfo", args=(debug_filename, debug_id))
        response = client.get(url)
        assert response.status_code == 200
        assert response.json() == {
            "debug_filename": debug_filename,
            "debug_id": debug_id,
            "code_file": code_file,
            "code_id": code_id,
            "generator": generator,
            "url": f"http://testserver/try/{debug_filename}/{debug_id}/{sym_file}",
        }
        metricsmock.assert_timing(
            "tecken.syminfo.lookup.timing", tags=["host:testnode"]
        )
        metricsmock.assert_incr(
            "tecken.syminfo.lookup.cached", tags=["result:false", "host:testnode"]
        )

    def test_lookup_failed(self, client, db, metricsmock):
        debug_filename = "xul.pdb"
        debug_id = "404B9729BE96C3CF4C4C44205044422E1"

        # Try syminfo with debug info
        url = reverse("api:syminfo", args=(debug_filename, debug_id))
        response = client.get(url)
        assert response.status_code == 404

        metricsmock.assert_timing(
            "tecken.syminfo.lookup.timing", tags=["host:testnode"]
        )
        metricsmock.assert_incr(
            "tecken.syminfo.lookup.cached", tags=["result:false", "host:testnode"]
        )

    def test_debuginfo_lookup_double_record(self, client, db, metricsmock):
        sym_file = "xul.sym"
        debug_filename = "xul.pdb"
        debug_id = "404B9729BE96C3CF4C4C44205044422E1"
        code_file = "xul.dll"
        code_id = "64E130A115A30000"
        generator = "mozilla/dump_syms XYZ"

        # Create 2 records
        FileUpload.objects.create(
            bucket_name="publicbucket",
            key=f"v1/{debug_filename}/{debug_id}/{sym_file}",
            size=100,
            debug_filename=debug_filename,
            debug_id=debug_id,
            code_file=code_file,
            code_id=code_id,
            generator=generator,
        )
        FileUpload.objects.create(
            bucket_name="publicbucket",
            key=f"v1/{debug_filename}/{debug_id}/{sym_file}",
            size=100,
            debug_filename=debug_filename,
            debug_id=debug_id,
            code_file=code_file,
            code_id=code_id,
            generator=generator,
        )

        # Try syminfo with debug info
        url = reverse("api:syminfo", args=(debug_filename, debug_id))
        response = client.get(url)
        assert response.status_code == 200
        assert response.json() == {
            "debug_filename": debug_filename,
            "debug_id": debug_id,
            "code_file": code_file,
            "code_id": code_id,
            "generator": generator,
            "url": f"http://testserver/{debug_filename}/{debug_id}/{sym_file}",
        }

        metricsmock.assert_timing(
            "tecken.syminfo.lookup.timing", tags=["host:testnode"]
        )
        metricsmock.assert_incr(
            "tecken.syminfo.lookup.cached", tags=["result:false", "host:testnode"]
        )

    def test_debuginfo_lookup_cached(self, client, db, metricsmock):
        sym_file = "xul.sym"
        debug_filename = "xul.pdb"
        debug_id = "404B9729BE96C3CF4C4C44205044422E1"
        code_file = "xul.dll"
        code_id = "64E130A115A30000"
        generator = "mozilla/dump_syms XYZ"

        FileUpload.objects.create(
            bucket_name="publicbucket",
            key=f"v1/{debug_filename}/{debug_id}/{sym_file}",
            size=100,
            debug_filename=debug_filename,
            debug_id=debug_id,
            code_file=code_file,
            code_id=code_id,
            generator=generator,
        )

        # Try syminfo with debug info
        url = reverse("api:syminfo", args=(debug_filename, debug_id))
        response = client.get(url)
        assert response.status_code == 200
        assert response.json() == {
            "debug_filename": debug_filename,
            "debug_id": debug_id,
            "code_file": code_file,
            "code_id": code_id,
            "generator": generator,
            "url": f"http://testserver/{debug_filename}/{debug_id}/{sym_file}",
        }

        metricsmock.assert_timing(
            "tecken.syminfo.lookup.timing", tags=["host:testnode"]
        )
        metricsmock.assert_incr(
            "tecken.syminfo.lookup.cached", tags=["result:false", "host:testnode"]
        )

        metricsmock.clear_records()

        # Request it again--this time it should come from cache
        response = client.get(url)
        assert response.status_code == 200
        assert response.json() == {
            "debug_filename": debug_filename,
            "debug_id": debug_id,
            "code_file": code_file,
            "code_id": code_id,
            "generator": generator,
            "url": f"http://testserver/{debug_filename}/{debug_id}/{sym_file}",
        }

        metricsmock.assert_timing(
            "tecken.syminfo.lookup.timing", tags=["host:testnode"]
        )
        metricsmock.assert_incr(
            "tecken.syminfo.lookup.cached", tags=["result:true", "host:testnode"]
        )

        metricsmock.clear_records()

        # Request it again--this time force a cache refresh
        response = client.get(url, {"_refresh": 1})
        assert response.status_code == 200
        assert response.json() == {
            "debug_filename": debug_filename,
            "debug_id": debug_id,
            "code_file": code_file,
            "code_id": code_id,
            "generator": generator,
            "url": f"http://testserver/{debug_filename}/{debug_id}/{sym_file}",
        }

        metricsmock.assert_timing(
            "tecken.syminfo.lookup.timing", tags=["host:testnode"]
        )
        metricsmock.assert_incr(
            "tecken.syminfo.lookup.cached", tags=["result:false", "host:testnode"]
        )
