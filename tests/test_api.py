# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json

import pytest

from django.contrib.auth.models import User, Permission, Group
from django.core.urlresolvers import reverse
from django.utils import timezone

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload
from tecken.download.models import MissingSymbol, MicrosoftDownload
from tecken.api.views import filter_uploads
from tecken.api.forms import UploadsForm


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
    assert not data['user']['is_superuser']
    assert data['user']['email']
    assert data['sign_out_url']
    assert not data['user']['permissions']

    permission = Permission.objects.get(codename='manage_tokens')
    user.user_permissions.add(permission)
    permission = Permission.objects.get(codename='upload_symbols')
    user.user_permissions.add(permission)

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert 'upload.upload_symbols' in [
        x['codename'] for x in data['user']['permissions']
    ]
    assert 'tokens.manage_tokens' in [
        x['codename'] for x in data['user']['permissions']
    ]


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
    assert response.status_code == 403

    permission = Permission.objects.get(codename='manage_tokens')
    user.user_permissions.add(permission)
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
def test_tokens_filtering(client):
    url = reverse('api:tokens')
    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')
    permission = Permission.objects.get(codename='manage_tokens')
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['tokens'] == []
    assert data['totals'] == {
        'active': 0,
        'all': 0,
        'expired': 0
    }

    # Create 2 tokens. One expired and one not expired.
    t1 = Token.objects.create(user=user, notes='current')
    assert not t1.is_expired
    yesterday = timezone.now() - datetime.timedelta(days=1)
    t2 = Token.objects.create(user=user, expires_at=yesterday, notes='gone')
    assert t2.is_expired

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert len(data['tokens']) == 1
    assert [x['notes'] for x in data['tokens']] == ['current']
    assert data['totals'] == {
        'active': 1,
        'all': 2,
        'expired': 1
    }

    # Filter on the expired ones
    response = client.get(url, {'state': 'expired'})
    assert response.status_code == 200
    data = response.json()
    assert len(data['tokens']) == 1
    assert [x['notes'] for x in data['tokens']] == ['gone']

    # Filter on 'all'
    response = client.get(url, {'state': 'all'})
    assert response.status_code == 200
    data = response.json()
    assert len(data['tokens']) == 2
    assert [x['notes'] for x in data['tokens']] == ['gone', 'current']

    # Filter incorrectly
    response = client.get(url, {'state': 'junks'})
    assert response.status_code == 400


@pytest.mark.django_db
def test_tokens_create(client):
    url = reverse('api:tokens')
    response = client.post(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    permission = Permission.objects.get(codename='manage_tokens')
    user.user_permissions.add(permission)
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
    group, = found_user['groups']
    assert group['name'] == 'Uploaders'
    user_permissions_names = [x['name'] for x in found_user['permissions']]
    assert 'Upload Symbols Files' in user_permissions_names
    assert 'Manage Your API Tokens' in user_permissions_names


@pytest.mark.django_db
def test_users_permissions(client):
    """when you query all users, for each user it lists all the permissions.
    This is done by "expanding" each user's groups' permissions.
    But it must repeat permissions that are found in multiple groups.
    """
    # log in as a superuser.
    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.is_superuser = True
    user.save()
    assert client.login(username='peterbe', password='secret')

    # Create a second user we're going to manipulate.
    user = User.objects.create(username='you', email='you@example.com')
    # Both of these groups have overlapping permissions.
    # Namely, they both imply the 'Manage Your API Tokens' permission.
    user.groups.add(Group.objects.get(name='Uploaders'))
    user.groups.add(Group.objects.get(name='Upload Auditors'))

    url = reverse('api:users')
    response = client.get(url)
    assert response.status_code == 200
    user_record, = [x for x in response.json()['users'] if x['id'] == user.id]
    user_permissions_names = [x['name'] for x in user_record['permissions']]
    assert 'Manage Your API Tokens' in user_permissions_names
    assert 'View All Symbols Uploads' in user_permissions_names
    assert 'Upload Symbols Files' in user_permissions_names


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


@pytest.mark.django_db
def test_edit_user_permissions(client):
    """user permissions is a bit more non-trivial so this test is all about
    changing a users permissions (done by adding/removing groups)."""

    # log in as a superuser.
    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.is_superuser = True
    user.save()
    assert client.login(username='peterbe', password='secret')

    # Create a second user we're going to manipulate.
    user = User.objects.create(username='you', email='you@example.com')
    url = reverse('api:edit_user', args=(user.id,))
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()['user']['groups'] == []
    # The JSON response will also contain a list of all possible groups.
    # These should be the ones hardcoded in the apps' model Metas.
    all_group_names = [x['name'] for x in response.json()['groups']]
    assert 'Uploaders' in all_group_names
    assert 'Upload Auditors' in all_group_names

    # Make this user belong to "Uploaders" now
    response = client.post(url, {
        'is_active': True,
        'groups': Group.objects.get(name='Uploaders').id,
    })
    assert response.status_code == 200
    # assert user.groups.all().count() == 1
    assert user.groups.filter(name='Uploaders').exists()
    assert not user.groups.filter(name='Upload Auditors').exists()

    # Change our mind and make the user belong to the other one.
    response = client.post(url, {
        'is_active': True,
        'groups': Group.objects.get(name='Upload Auditors').id,
    })
    assert response.status_code == 200
    assert not user.groups.filter(name='Uploaders').exists()
    assert user.groups.filter(name='Upload Auditors').exists()


def test_uploadsform_dates():
    form = UploadsForm({
        'created_at': ''
    })
    assert form.is_valid()
    assert form.cleaned_data['created_at'] == []

    form = UploadsForm({
        'created_at': '2017-07-28'
    })
    assert form.is_valid()
    operator, value = form.cleaned_data['created_at'][0]
    assert operator == '='
    assert isinstance(value, datetime.datetime)
    assert value.tzinfo

    form = UploadsForm({
        'created_at': '>= 2017-07-28'
    })
    assert form.is_valid()
    operator, value = form.cleaned_data['created_at'][0]
    assert operator == '>='

    form = UploadsForm({
        'created_at': '<2017-07-26T14:01:41.956Z'
    })
    assert form.is_valid()
    operator, value = form.cleaned_data['created_at'][0]
    assert operator == '<'
    assert isinstance(value, datetime.datetime)
    assert value.tzinfo
    assert value.hour == 14

    form = UploadsForm({
        'created_at': '= null'
    })
    assert form.is_valid()
    operator, value = form.cleaned_data['created_at'][0]
    assert operator == '='
    assert value is None

    form = UploadsForm({
        'created_at': 'Incomplete'
    })
    assert form.is_valid()
    operator, value = form.cleaned_data['created_at'][0]
    assert operator == '='
    assert value is None

    # Now pass in some junk
    form = UploadsForm({
        'created_at': '2017-88-28'
    })
    assert not form.is_valid()
    form = UploadsForm({
        'created_at': '%2017-01-23'
    })
    assert not form.is_valid()

    form = UploadsForm({
        'created_at': 'Today'
    })
    assert form.is_valid()
    operator, value = form.cleaned_data['created_at'][0]
    assert operator == '='
    now = timezone.now()
    assert value.strftime('%Y%m%d') == now.strftime('%Y%m%d')

    form = UploadsForm({
        'created_at': 'yesterDAY'
    })
    assert form.is_valid()
    operator, value = form.cleaned_data['created_at'][0]
    assert operator == '='
    yesterday = now - datetime.timedelta(days=1)
    assert value.strftime('%Y%m%d') == yesterday.strftime('%Y%m%d')


def test_uploadsform_size():
    form = UploadsForm({
        'size': ''
    })
    assert form.is_valid()
    assert form.cleaned_data['size'] == []

    form = UploadsForm({
        'size': '1234'
    })
    assert form.is_valid()
    operator, value = form.cleaned_data['size'][0]
    assert operator == '='
    assert value == 1234

    form = UploadsForm({
        'size': '>=10MB'
    })
    assert form.is_valid()
    operator, value = form.cleaned_data['size'][0]
    assert operator == '>='
    assert value == 10 * 1024 * 1024


@pytest.mark.django_db
def test_uploadsform_user():
    form = UploadsForm({
        'user': 'peterbe'
    })
    assert not form.is_valid()
    # happens because of this...
    assert not User.objects.filter(email__icontains='peterbe').exists()

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    form = UploadsForm({
        'user': 'peterbe'
    })
    assert form.is_valid()
    assert form.cleaned_data['user'][0] == '='
    assert form.cleaned_data['user'][1] == user

    # Negate
    form = UploadsForm({
        'user': '!peterbe'
    })
    assert form.is_valid()
    assert form.cleaned_data['user'][0] == '!'
    assert form.cleaned_data['user'][1] == user


@pytest.mark.django_db
def test_uploads(client):
    url = reverse('api:uploads')
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['uploads'] == []
    assert not data['can_view_all']

    # Don't mess with the 'page' key
    response = client.get(url, {'page': 'notanumber'})
    assert response.status_code == 400
    # If you make it 0 or less, it just sends you to page 1
    response = client.get(url, {'page': '0'})
    assert response.status_code == 200

    # Let's pretend there's an upload belonging to someone else
    upload = Upload.objects.create(
        user=User.objects.create(email='her@example.com'),
        size=123456
    )
    # sanity check
    assert upload.created_at
    assert not upload.completed_at

    # Also, let's pretend there's at least one file upload
    FileUpload.objects.create(
        upload=upload,
        size=1234,
        key='foo.sym',
    )

    # Even if there is an upload, because you don't have permission
    # yet, it should not show up.
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['uploads'] == []

    permission = Permission.objects.get(codename='view_all_uploads')
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['uploads'][0]['id'] == upload.id
    assert data['uploads'][0]['files_count'] == 1
    assert data['can_view_all']

    # Now you can search for anybody's uploads
    response = client.get(url, {'user': 'HER@'})
    assert response.status_code == 200
    data = response.json()
    assert data['uploads'][0]['id'] == upload.id

    # The 'user' has to match exactly 1 user
    response = client.get(url, {'user': 'neverheardof'})
    assert response.status_code == 400
    assert response.json()['errors']['user']
    User.objects.create(email='nother@example.com', username='nother')
    # Now this becomes ambiguous
    response = client.get(url, {'user': 'her@'})
    assert response.status_code == 400
    assert response.json()['errors']['user']
    # Be specific this time
    response = client.get(url, {'user': 'her@example.com'})
    assert response.status_code == 200
    assert data['uploads'][0]['id'] == upload.id
    # Anybody elses uploads
    response = client.get(url, {'user': '! her@example.com'})
    assert response.status_code == 200
    assert not response.json()['uploads']  # expect it to be empty

    # Filter incorrectly
    response = client.get(url, {'size': '>= xxx'})
    assert response.status_code == 400
    assert response.json()['errors']['size']

    # Let's filter on size
    response = client.get(url, {'size': '>= 10KB'})
    assert response.status_code == 200
    data = response.json()
    assert data['uploads'][0]['id'] == upload.id
    response = client.get(url, {'size': '< 1000'})
    assert response.status_code == 200
    data = response.json()
    assert not data['uploads']
    # Filter on "multiple sizes"
    response = client.get(url, {'size': '>= 10KB, < 1g'})
    assert response.status_code == 200
    data = response.json()
    assert data['uploads'][0]['id'] == upload.id

    # Let's filter on dates
    response = client.get(url, {
        'created_at': '>' + upload.created_at.date().strftime('%Y-%m-%d'),
        'completed_at': 'Incomplete',
    })
    assert response.status_code == 200
    data = response.json()
    assert data['uploads'][0]['id'] == upload.id
    # Filter on a specific *day* is exceptional
    response = client.get(url, {
        'created_at': upload.created_at.date().strftime('%Y-%m-%d'),
    })
    assert response.status_code == 200
    data = response.json()
    assert data['uploads'][0]['id'] == upload.id
    day_before = upload.created_at - datetime.timedelta(days=1)
    response = client.get(url, {
        'created_at': day_before.strftime('%Y-%m-%d'),
    })
    assert response.status_code == 200
    data = response.json()
    assert not data['uploads']


@pytest.mark.django_db
def test_uploads_second_increment(client):
    """If you query uploads with '?created_at=>SOMEDATE' that date
    gets an extra second added to it. That's because the datetime objects
    are stored in the ORM with microseconds but in JSON dumps (isoformat())
    the date loses that accuracy and if you take the lates upload's
    'created_at' and use the '>' operator it shouldn't be included."""
    url = reverse('api:uploads')
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    permission = Permission.objects.get(codename='view_all_uploads')
    user.user_permissions.add(permission)
    assert client.login(username='peterbe', password='secret')

    Upload.objects.create(
        user=User.objects.create(email='her@example.com'),
        size=123456
    )

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 1

    last_created_at = data['uploads'][0]['created_at']
    response = client.get(url, {
        'created_at': f'>{last_created_at}'
    })
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 0

    # But if you use '>=' operator it should be fine and it should be included.
    response = client.get(url, {
        'created_at': f'>={last_created_at}'
    })
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 1


@pytest.mark.django_db
def test_upload(client):
    url = reverse('api:upload', args=(9999999,))
    response = client.get(url)
    # Won't even let you in to find out that ID doesn't exist.
    assert response.status_code == 403

    # What if you're signed in
    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get(url)
    # Won't even let you in to find out that ID doesn't exist.
    assert response.status_code == 404

    upload = Upload.objects.create(
        user=User.objects.create(email='her@example.com'),
        size=123456,
        skipped_keys=['foo'],
        ignored_keys=['bar'],
    )
    FileUpload.objects.create(
        upload=upload,
        size=1234,
        key='foo.sym',
    )
    url = reverse('api:upload', args=(upload.id,))
    response = client.get(url)
    # You can't view it because you don't have access to it.
    assert response.status_code == 403

    permission = Permission.objects.get(codename='view_all_uploads')
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200

    result = response.json()
    assert result['upload']['id'] == upload.id
    assert result['upload']['user']['email'] == upload.user.email
    assert result['upload']['related'] == []
    first_file_upload, = result['upload']['file_uploads']
    assert first_file_upload['size'] == 1234


@pytest.mark.django_db
def test_upload_related(client):
    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    permission = Permission.objects.get(codename='view_all_uploads')
    user.user_permissions.add(permission)
    assert client.login(username='peterbe', password='secret')

    upload = Upload.objects.create(
        user=User.objects.create(email='her@example.com'),
        size=123456,
        skipped_keys=['foo'],
        ignored_keys=['bar'],
        filename='symbols.zip',
    )
    FileUpload.objects.create(
        upload=upload,
        size=1234,
        key='foo.sym',
    )

    upload2 = Upload.objects.create(
        user=upload.user,
        size=upload.size,
        filename=upload.filename,
    )

    url = reverse('api:upload', args=(upload.id,))
    response = client.get(url)
    assert response.status_code == 200
    result = response.json()
    assert result['upload']['related'][0]['id'] == upload2.id

    upload3 = Upload.objects.create(
        user=upload.user,
        size=upload.size,
        filename='different.zip',
        content_hash='deadbeef123'
    )
    upload.content_hash = upload3.content_hash
    upload.save()
    response = client.get(url)
    assert response.status_code == 200
    result = response.json()
    assert result['upload']['related'][0]['id'] == upload3.id


@pytest.mark.django_db
def test_upload_files(client, settings):
    url = reverse('api:upload_files')
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get(url)
    assert response.status_code == 403

    permission = Permission.objects.get(codename='view_all_uploads')
    user.user_permissions.add(permission)
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['files'] == []

    # Don't mess with the 'page' key
    response = client.get(url, {'page': 'notanumber'})
    assert response.status_code == 400

    # Let's pretend there's an upload belonging to someone else
    upload = Upload.objects.create(
        user=User.objects.create(email='her@example.com'),
        size=123456
    )
    # sanity check
    assert upload.created_at
    assert not upload.completed_at
    # Also, let's pretend there's at least one file upload
    file_upload1 = FileUpload.objects.create(
        upload=upload,
        size=1234,
        bucket_name='symbols-private',
        key='v0/bar.dll/A4FC12EFA5/foo.sym',
    )
    # Make a FileUpload that is not associated with an upload and
    # is a microsoft download.
    file_upload2 = FileUpload.objects.create(
        size=100,
        key='v0/foo.pdb/deadbeef/foo.sym',
        compressed=True,
        bucket_name='symbols-public',
        microsoft_download=True
    )

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['files']
    all_ids = set([file_upload1.id, file_upload2.id])
    assert set(x['id'] for x in data['files']) == all_ids
    assert data['batch_size'] == settings.API_FILES_BATCH_SIZE
    assert data['total'] == 2
    # Check the 'upload' which should either be None or a dict
    for file_upload in data['files']:
        if file_upload['id'] == file_upload1.id:
            assert file_upload['upload']['id'] == upload.id
            assert file_upload['upload']['user']['id'] == upload.user.id
            assert file_upload['upload']['created_at']
        else:
            assert file_upload['upload'] is None
    # Check that there are some aggregates
    aggregates = data['aggregates']
    assert aggregates['files']['count'] == 2
    assert aggregates['files']['incomplete'] == 2
    assert aggregates['files']['size']['sum'] == 1234 + 100

    # Filter by created_at and completed_at
    response = client.get(url, {
        'created_at': '>' + upload.created_at.date().strftime('%Y-%m-%d'),
        'completed_at': 'Incomplete',
    })
    assert response.status_code == 200
    data = response.json()
    assert set(x['id'] for x in data['files']) == all_ids

    tomorrow = file_upload1.created_at + datetime.timedelta(
        days=1
    )
    file_upload1.completed_at = tomorrow
    file_upload1.save()
    response = client.get(url, {
        'completed_at': tomorrow.strftime('%Y-%m-%d'),
    })
    assert response.status_code == 200
    data = response.json()
    assert [x['id'] for x in data['files']] == [file_upload1.id]

    # Let's filter on size
    response = client.get(url, {'size': '>= 1KB'})
    assert response.status_code == 200
    data = response.json()
    assert [x['id'] for x in data['files']] == [file_upload1.id]

    # Filter by key
    response = client.get(url, {
        'key': 'foo.sym',
    })
    assert response.status_code == 200
    data = response.json()
    assert set(x['id'] for x in data['files']) == all_ids
    response = client.get(url, {
        'key': 'foo.sym, deadbeef',
    })
    assert response.status_code == 200
    data = response.json()
    assert [x['id'] for x in data['files']] == [file_upload2.id]

    # Search by download=microsoft
    response = client.get(url, {
        'download': 'microsoft',
    })
    assert response.status_code == 200
    data = response.json()
    assert [x['id'] for x in data['files']] == [file_upload2.id]
    # But it's picky about that value
    response = client.get(url, {
        'download': 'Something else',
    })
    assert response.status_code == 400

    # Filter by bucket_name
    response = client.get(url, {
        'bucket_name': file_upload1.bucket_name,
    })
    assert response.status_code == 200
    data = response.json()
    assert [x['id'] for x in data['files']] == [file_upload1.id]
    # By negated bucket name
    response = client.get(url, {
        'bucket_name': f'!{file_upload1.bucket_name}',
    })
    assert response.status_code == 200
    data = response.json()
    assert [x['id'] for x in data['files']] == [file_upload2.id]


@pytest.mark.django_db
def test_stats(client):
    # This view isn't super important so we'll just make sure it runs at all
    url = reverse('api:stats')
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['stats']['uploads']
    assert not data['stats']['uploads']['all_uploads']
    assert 'users' not in data['stats']
    assert data['stats']['tokens']

    user.is_superuser = True
    user.save()

    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['stats']['users']
    assert data['stats']['uploads']['all_uploads']


@pytest.mark.django_db
def test_current_settings(client, settings):
    settings.SYMBOL_URLS = [
        'https://awsamazon.com/default-bucket-name',
        'https://username:password@awsamazon.com/other-bucket-name'
    ]
    url = reverse('api:current_settings')
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get(url)
    assert response.status_code == 403

    user.is_superuser = True
    user.save()
    response = client.get(url)
    assert response.status_code == 200
    current_settings = {
        x['key']: x['value'] for x in response.json()['settings']
    }
    assert current_settings['SYMBOL_URLS'] == json.dumps([
        'https://awsamazon.com/default-bucket-name',
        'https://user:xxxxxx@awsamazon.com/other-bucket-name',
    ])


@pytest.mark.django_db
def test_current_versions(client):
    url = reverse('api:current_versions')
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get(url)
    assert response.status_code == 403

    user.is_superuser = True
    user.save()
    response = client.get(url)
    assert response.status_code == 200
    current_versions = {
        x['key']: x['value'] for x in response.json()['versions']
    }
    assert 'Django' in current_versions
    assert 'Tecken' in current_versions
    assert 'PostgreSQL' in current_versions
    assert 'Redis Cache' in current_versions
    assert 'Redis Store' in current_versions


@pytest.mark.django_db
def test_filter_uploads_by_size():
    """Test the utility function filter_uploads()"""
    user1 = User.objects.create(email='test@example.com')
    Upload.objects.create(
        user=user1,
        filename='symbols1.zip',
        size=1234
    )
    form = UploadsForm({})
    assert form.is_valid()
    qs = Upload.objects.all()
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 1

    form = UploadsForm({'size': '>1234'})
    assert form.is_valid()
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 0

    form = UploadsForm({'size': '>=1234'})
    assert form.is_valid()
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 1

    form = UploadsForm({'size': '>1Kb'})
    assert form.is_valid()
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 1


@pytest.mark.django_db
def test_filter_uploads_by_user():
    """Test the utility function filter_uploads()"""
    user1 = User.objects.create(username='test1')
    Upload.objects.create(
        user=user1,
        filename='symbols1.zip',
        size=1234
    )
    user2 = User.objects.create(username='test2')
    Upload.objects.create(
        user=user2,
        filename='symbols2.zip',
        size=123456789
    )
    qs = Upload.objects.all()
    form = UploadsForm({})
    assert form.is_valid()
    assert filter_uploads(
        qs,
        False,
        user1,
        form
    ).count() == 1
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 2

    user3 = User.objects.create(username='test3')
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 2
    assert filter_uploads(
        qs,
        False,
        user3,
        form
    ).count() == 0


@pytest.mark.django_db
def test_filter_uploads_by_completed_at():
    """Test the utility function filter_uploads()"""
    user1 = User.objects.create(username='test1')
    Upload.objects.create(
        user=user1,
        filename='symbols1.zip',
        size=1234,
    )
    Upload.objects.create(
        user=user1,
        filename='symbols2.zip',
        size=1234,
        completed_at=timezone.now()
    )
    qs = Upload.objects.all()

    form = UploadsForm({'completed_at': 'Incomplete'})
    assert form.is_valid()
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 1

    form = UploadsForm({'completed_at': 'today'})
    assert form.is_valid()
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 1

    form = UploadsForm({'completed_at': '<2017-10-09'})
    assert form.is_valid()
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 0

    today = timezone.now()
    form = UploadsForm({'completed_at': today.strftime('%Y-%m-%d')})
    assert form.is_valid()
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 1

    form = UploadsForm({'completed_at': '>' + today.isoformat()})
    assert form.is_valid()
    assert filter_uploads(
        qs,
        True,
        user1,
        form
    ).count() == 0


@pytest.mark.django_db
def test_uploads_datasets(client):
    url = reverse('api:uploads_datasets')
    response = client.get(url)
    assert response.status_code == 403

    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get(url)
    assert response.status_code == 200
    assert len(response.json()['datasets']) == 3

    # XXX this test clearly doesn't test much of the actual data
    # gathering in those datasets. However, it works!
    # We could extend this by creating more Upload and File objects
    # and re-run and look at the data. Doesn't feel super user at the moment.


@pytest.mark.django_db
def test_downloads_missing(client):
    url = reverse('api:downloads_missing')
    response = client.get(url)
    data = response.json()
    assert data['missing'] == []
    assert data['total'] == 0

    MissingSymbol.objects.create(
        hash='x1',
        symbol='foo.pdb',
        debugid='ADEF12345',
        filename='foo.sym',
        count=1
    )
    MissingSymbol.objects.create(
        hash='x2',
        symbol='foo.pdb',
        debugid='01010101',
        filename='foo.ex_',
        count=2
    )
    response = client.get(url)
    data = response.json()
    assert data['total'] == 2

    # Filter by modified_at
    response = client.get(url, {
        'modified_at': timezone.now().isoformat()
    })
    data = response.json()
    assert data['total'] == 0
    response = client.get(url, {
        'modified_at': '<' + timezone.now().isoformat()
    })
    data = response.json()
    assert data['total'] == 2

    # Filter by count
    response = client.get(url, {
        'count': '>1'
    })
    data = response.json()
    assert data['total'] == 1

    # Filter by debugid
    response = client.get(url, {
        'debugid': 'xxx'
    })
    data = response.json()
    assert data['total'] == 0
    response = client.get(url, {
        'debugid': 'ADEF12345'
    })
    data = response.json()
    assert data['total'] == 1
    assert data['missing'][0]['debugid'] == 'ADEF12345'

    # Filter by count
    response = client.get(url, {
        'count': '>1'
    })
    data = response.json()
    assert data['total'] == 1
    assert data['missing'][0]['filename'] == 'foo.ex_'
    response = client.get(url, {
        'count': '2'
    })
    data = response.json()
    assert data['total'] == 1
    assert data['missing'][0]['filename'] == 'foo.ex_'

    # Bad form input
    response = client.get(url, {
        'modified_at': 'not a date'
    })
    assert response.status_code == 400
    assert response.json()['errors']['modified_at']
    response = client.get(url, {
        'count': 'not a number'
    })
    assert response.status_code == 400
    assert response.json()['errors']['count']

    # Bad pagination
    response = client.get(url, {
        'page': 'not a number'
    })
    assert response.status_code == 400
    assert response.json()['errors']['page']


@pytest.mark.django_db
def test_downloads_microsoft(client):
    url = reverse('api:downloads_microsoft')
    response = client.get(url)
    data = response.json()
    assert data['microsoft_downloads'] == []
    assert data['aggregates']['microsoft_downloads']['total'] == 0
    assert data['total'] == 0

    MicrosoftDownload.objects.create(
        missing_symbol=MissingSymbol.objects.create(
            hash='x1',
            symbol='foo.pdb',
            debugid='ADEF12345',
            filename='foo.sym',
            count=1
        ),
        url='https://msdn.example.com/foo.sym',
        file_upload=FileUpload.objects.create(
            bucket_name='mybucket',
            key='v0/foo.pdb/ADEF12345/foo.sym',
            update=False,
            compressed=True,
            size=12345,
            microsoft_download=True,
            completed_at=timezone.now(),
        ),
        skipped=False,
        completed_at=timezone.now(),
    )
    MicrosoftDownload.objects.create(
        missing_symbol=MissingSymbol.objects.create(
            hash='x2',
            symbol='foo.pdb',
            debugid='01010101',
            filename='foo.ex_',
            count=2
        ),
        url='https://msdn.example.com/foo2.sym',
        error='Something terrible!',
        completed_at=timezone.now(),
    )

    response = client.get(url)
    data = response.json()
    assert data['total'] == 2

    # Filter by created_at
    response = client.get(url, {
        'created_at': timezone.now().isoformat()
    })
    data = response.json()
    assert data['total'] == 0
    response = client.get(url, {
        'created_at': '<' + timezone.now().isoformat()
    })
    data = response.json()
    assert data['total'] == 2

    # Filter by symbol
    response = client.get(url, {
        'symbol': 'foo.pdb'
    })
    data = response.json()
    assert data['total'] == 2

    # Filter by filename
    response = client.get(url, {
        'filename': 'foo.sym'
    })
    data = response.json()
    assert data['total'] == 1
    first_missing_symbol = data['microsoft_downloads'][0]
    assert first_missing_symbol['missing_symbol']['filename'] == 'foo.sym'

    # Filter by specific error
    response = client.get(url, {
        'state': 'specific-error',
        'error': 'terrible'
    })
    data = response.json()
    assert data['total'] == 1
    response = client.get(url, {
        'state': 'specific-error',
        'error': 'not found'
    })
    data = response.json()
    assert data['total'] == 0

    # Filter by those errored
    response = client.get(url, {
        'state': 'errored',
    })
    data = response.json()
    assert data['total'] == 1
    assert data['microsoft_downloads'][0]['error'] == 'Something terrible!'

    # Filter by those that have a file upload
    response = client.get(url, {
        'state': 'file-upload',
    })
    data = response.json()
    assert data['total'] == 1

    # Those that don't have a file upload
    response = client.get(url, {
        'state': 'no-file-upload',
    })
    data = response.json()
    assert data['total'] == 1

    # Form validation failure
    response = client.get(url, {
        'created_at': 'not a date',
    })
    assert response.status_code == 400
    assert response.json()['errors']['created_at']

    # Bad pagination
    response = client.get(url, {
        'page': 'not a number'
    })
    assert response.status_code == 400
    assert response.json()['errors']['page']
