# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime

import pytest

from django.contrib.auth.models import User, Permission
from django.urls import reverse
from django.utils import timezone

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload, UploadsCreated
from tecken.download.models import MissingSymbol
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
def test_uploads_separate_endpoints(client):
    user = User.objects.create(username="efilho", email="efilho@example.com")
    user.set_password("secret")
    user.save()
    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)
    assert client.login(username="efilho", password="secret")

    # Content endpoint
    url = reverse("api:uploads_content")
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert "uploads" in data
    assert "batch_size" in data
    assert "order_by" in data
    assert "can_view_all" in data
    assert "has_next" in data
    assert "aggregates" not in data
    assert "total" not in data

    url = reverse("api:uploads_aggregates")
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "aggregates" in data
    assert "uploads" not in data
    assert "batch_size" not in data
    assert "order_by" not in data
    assert "can_view_all" not in data
    assert "has_next" not in data


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
    UploadsCreated.update(timezone.now().date())

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1

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
def test_uploads_created(client):
    url = reverse("api:uploads_created")
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.get(url)
    assert response.status_code == 403

    permission = Permission.objects.get(codename="view_all_uploads")
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["uploads_created"] == []

    # Don't mess with the 'page' key
    response = client.get(url, {"page": "notanumber"})
    assert response.status_code == 400
    # If you make it 0 or less, it just sends you to page 1
    response = client.get(url, {"page": "0"})
    assert response.status_code == 200

    now = timezone.now()
    upload_created = UploadsCreated.objects.create(
        date=now.date(),
        count=12,
        files=1000,
        skipped=10,
        ignored=5,
        size=500_000_000,
        size_avg=500_000,
    )

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["uploads_created"][0]["id"] == upload_created.id
    assert data["uploads_created"][0]["date"] == now.strftime("%Y-%m-%d")
    assert data["uploads_created"][0]["count"] == 12
    assert data["uploads_created"][0]["files"] == 1000
    assert data["uploads_created"][0]["skipped"] == 10
    assert data["uploads_created"][0]["ignored"] == 5
    assert data["uploads_created"][0]["size"] == 500_000_000
    assert data["uploads_created"][0]["size_avg"] == 500_000

    # Filter incorrectly
    response = client.get(url, {"size": ">= xxx"})
    assert response.status_code == 400
    assert response.json()["errors"]["size"]

    # Let's filter on size
    response = client.get(url, {"size": ">= 10KB"})
    assert response.status_code == 200
    data = response.json()
    assert data["uploads_created"][0]["id"] == upload_created.id
    assert data["total"] == 1

    response = client.get(url, {"size": "< 1000"})
    assert response.status_code == 200
    data = response.json()
    assert not data["uploads_created"]
    assert data["total"] == 0

    # Filter on "multiple sizes"
    response = client.get(url, {"size": ">= 10KB, < 1g"})
    assert response.status_code == 200
    data = response.json()
    assert data["uploads_created"][0]["id"] == upload_created.id

    # Let's filter on dates
    response = client.get(url, {"date": ">=" + now.strftime("%Y-%m-%d")})
    assert response.status_code == 200
    data = response.json()
    assert data["uploads_created"][0]["id"] == upload_created.id

    # Filter on count (negative)
    response = client.get(url, {"count": "-1"})
    assert response.status_code == 400
    data = response.json()
    assert data["errors"]["count"]

    # Filter on count (not an integer)
    response = client.get(url, {"count": "notanumber"})
    assert response.status_code == 400
    data = response.json()
    assert data["errors"]["count"]

    response = client.get(url, {"count": ">1"})
    assert response.status_code == 200
    data = response.json()
    assert data["uploads_created"]

    response = client.get(url, {"count": ">12"})
    assert response.status_code == 200
    data = response.json()
    assert not data["uploads_created"]


@pytest.mark.django_db
def test_uploads_created_backfilled(client):
    url = reverse("api:uploads_created_backfilled")
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    # Create some fake uploads
    Upload.objects.create(user=user, size=10_000_000)

    response = client.get(url)
    assert response.status_code == 403

    user.is_superuser = True
    user.save()
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert not data["backfilled"]

    response = client.post(url)
    assert response.status_code == 200
    data = response.json()
    assert data["updated"]
    assert data["backfilled"]


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

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

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
        user=User.objects.create(email="her@example.com"), size=123_456
    )
    # Confidence check
    assert upload.created_at
    assert not upload.completed_at
    # Also, let's pretend there's at least one file upload
    file_upload1 = FileUpload.objects.create(
        upload=upload,
        size=1234,
        bucket_name="symbols-private",
        key="v0/bar.dll/A4FC12EFA5/foo.sym",
    )
    file_upload2 = FileUpload.objects.create(
        size=100,
        key="v0/foo.pdb/deadbeef/foo.sym",
        compressed=True,
        bucket_name="symbols-public",
    )

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["files"]
    all_ids = {file_upload1.id, file_upload2.id}
    assert {x["id"] for x in data["files"]} == all_ids
    assert data["batch_size"] == settings.API_FILES_BATCH_SIZE
    assert data["total"] == 2
    # Check the 'upload' which should either be None or a dict
    for file_upload in data["files"]:
        if file_upload["id"] == file_upload1.id:
            assert file_upload["upload"]["id"] == upload.id
            assert file_upload["upload"]["user"]["id"] == upload.user.id
            assert file_upload["upload"]["created_at"]
        else:
            assert file_upload["upload"] is None
    # Check that there are some aggregates
    aggregates = data["aggregates"]
    assert aggregates["files"]["count"] == 2
    assert aggregates["files"]["incomplete"] == 2
    assert aggregates["files"]["size"]["sum"] == 1234 + 100

    url_content = reverse("api:upload_files_content")
    # Must return only "content" data
    response = client.get(url_content)
    assert response.status_code == 200
    data = response.json()
    assert data["files"]
    assert data["batch_size"] == settings.API_FILES_BATCH_SIZE
    assert data["has_next"] is False
    assert "aggregates" not in data
    assert "total" not in data

    url_aggregates = reverse("api:upload_files_aggregates")
    # Must return only "aggregates" data
    response = client.get(url_aggregates)
    assert response.status_code == 200
    data = response.json()
    assert data["aggregates"]
    assert "files" not in data
    aggregates = data["aggregates"]
    assert data["total"] == 2
    assert aggregates["files"]["count"] == 2
    assert aggregates["files"]["incomplete"] == 2
    assert aggregates["files"]["size"]["sum"] == 1234 + 100

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
    response = client.get(url, {"key": "foo.sym"})
    assert response.status_code == 200
    data = response.json()
    assert {x["id"] for x in data["files"]} == all_ids
    response = client.get(url, {"key": "foo.sym, deadbeef"})
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
    assert data["stats"]["uploads"]
    assert not data["stats"]["uploads"]["all_uploads"]
    assert "users" not in data["stats"]
    assert data["stats"]["tokens"]

    user.is_superuser = True
    user.save()

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["stats"]["users"]
    assert data["stats"]["uploads"]["all_uploads"]


@pytest.mark.django_db
def test_stats_missing_symbols_count(client):
    url = reverse("api:stats")
    response = client.get(url)
    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    missing = data["stats"]["downloads"]["missing"]
    assert missing["today"]["count"] == 0
    assert missing["yesterday"]["count"] == 0
    assert missing["last_30_days"]["count"] == 0

    MissingSymbol.objects.create(
        hash="x1", symbol="foo.pdb", debugid="ADEF12345", filename="foo.sym", count=1
    )
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    missing = data["stats"]["downloads"]["missing"]
    assert missing["today"]["count"] == 1
    assert missing["yesterday"]["count"] == 0
    assert missing["last_30_days"]["count"] == 1


@pytest.mark.django_db
def test_stats_uploads(client):
    url = reverse("api:stats_uploads")
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username="peterbe", email="peterbe@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="peterbe", password="secret")

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()

    assert data["uploads"]["today"]["count"] == 0
    assert data["uploads"]["today"]["files"] == 0
    assert data["uploads"]["today"]["total_size"] == 0
    assert data["uploads"]["today"]["total_size_human"] == "0 bytes"
    assert data["uploads"]["yesterday"]["count"] == 0
    assert data["uploads"]["yesterday"]["files"] == 0
    assert data["uploads"]["yesterday"]["total_size"] == 0
    assert data["uploads"]["yesterday"]["total_size_human"] == "0 bytes"
    assert data["uploads"]["this_month"]["count"] == 0
    assert data["uploads"]["this_month"]["files"] == 0
    assert data["uploads"]["this_month"]["total_size"] == 0
    assert data["uploads"]["this_month"]["total_size_human"] == "0 bytes"

    UploadsCreated.objects.create(
        date=timezone.now().date(),
        count=3,
        size=123_456_789,
        size_avg=500_000,
        files=100,
        skipped=1,
        ignored=2,
    )

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()

    assert data["uploads"]["today"]["count"] == 3
    assert data["uploads"]["today"]["files"] == 100
    assert data["uploads"]["today"]["total_size"] == 123_456_789
    assert data["uploads"]["today"]["total_size_human"] == "117.7 MB"
    assert data["uploads"]["yesterday"]["count"] == 0
    assert data["uploads"]["yesterday"]["files"] == 0
    assert data["uploads"]["yesterday"]["total_size"] == 0
    assert data["uploads"]["yesterday"]["total_size_human"] == "0 bytes"
    assert data["uploads"]["this_month"]["count"] == 3
    assert data["uploads"]["this_month"]["files"] == 100
    assert data["uploads"]["this_month"]["total_size"] == 123_456_789
    assert data["uploads"]["this_month"]["total_size_human"] == "117.7 MB"


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
def test_downloads_missing(client):
    url = reverse("api:downloads_missing")
    response = client.get(url)
    data = response.json()
    assert data["missing"] == []
    assert data["total"] == 0

    MissingSymbol.objects.create(
        hash="x1", symbol="foo.pdb", debugid="ADEF12345", filename="foo.sym", count=1
    )
    MissingSymbol.objects.create(
        hash="x2", symbol="foo.pdb", debugid="01010101", filename="foo.ex_", count=2
    )
    response = client.get(url)
    data = response.json()
    assert data["total"] == 2

    # Filter by modified_at
    response = client.get(url, {"modified_at": timezone.now().isoformat()})
    data = response.json()
    assert data["total"] == 0
    response = client.get(url, {"modified_at": "<" + timezone.now().isoformat()})
    data = response.json()
    assert data["total"] == 2

    # Filter by count
    response = client.get(url, {"count": ">1"})
    data = response.json()
    assert data["total"] == 1

    # Filter by debugid
    response = client.get(url, {"debugid": "xxx"})
    data = response.json()
    assert data["total"] == 0
    response = client.get(url, {"debugid": "ADEF12345"})
    data = response.json()
    assert data["total"] == 1
    assert data["missing"][0]["debugid"] == "ADEF12345"

    # Filter by count
    response = client.get(url, {"count": ">1"})
    data = response.json()
    assert data["total"] == 1
    assert data["missing"][0]["filename"] == "foo.ex_"
    response = client.get(url, {"count": "2"})
    data = response.json()
    assert data["total"] == 1
    assert data["missing"][0]["filename"] == "foo.ex_"

    # Bad form input
    response = client.get(url, {"modified_at": "not a date"})
    assert response.status_code == 400
    assert response.json()["errors"]["modified_at"]
    response = client.get(url, {"count": "not a number"})
    assert response.status_code == 400
    assert response.json()["errors"]["count"]

    # Bad pagination
    response = client.get(url, {"page": "not a number"})
    assert response.status_code == 400
    assert response.json()["errors"]["page"]


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
        upload=upload, size=1234, key="foo.pdb/deadbeaf123/foo.sym"
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
    assert data["url"] == "/foo.pdb/deadbeaf123/foo.sym"


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
    data = response.json()["file"]
    assert data["url"] == "/foo.pdb/deadbeaf123/foo.sym?try"


@pytest.mark.django_db
def test_possible_upload_urls(client, settings):
    # Set an exception to match the user we're creating
    public_bucket = "http://localstack:4566/public/?access=public"
    private_bucket = "http://localstack:4566/private/"

    settings.SYMBOL_URLS = [public_bucket]
    settings.UPLOAD_URL_EXCEPTIONS = {"*example.com": private_bucket}
    settings.UPLOAD_DEFAULT_URL = public_bucket

    url = reverse("api:possible_upload_urls")
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username="adminuser", email="adminuser@example.com")
    user.set_password("secret")
    user.save()
    assert client.login(username="adminuser", password="secret")

    response = client.get(url)
    assert response.status_code == 200
    urls = response.json()["urls"]
    assert urls == [
        {
            "bucket_name": "private",
            "default": False,
            "private": True,
            "url": private_bucket,
        }
    ]
