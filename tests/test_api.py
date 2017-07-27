# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime

import pytest

from django.contrib.auth.models import User, Permission, Group
from django.core.urlresolvers import reverse
from django.utils import timezone

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload
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
    assert 'upload_symbols' in data['user']['permissions']
    assert 'manage_tokens' in data['user']['permissions']


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
    User.objects.create(email='nother@example.com', username='nother')
    # Now this becomes ambiguous
    response = client.get(url, {'user': 'her@'})
    assert response.status_code == 400

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
    first_file_upload, = result['upload']['file_uploads']
    assert first_file_upload['size'] == 1234


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
