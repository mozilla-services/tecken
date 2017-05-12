# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import gzip
import os
import re
from io import BytesIO

import pytest
import mock
from botocore.exceptions import ClientError

from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload
from tecken.upload.tasks import upload_inbox_upload
from tecken.upload.views import get_bucket_info


_here = os.path.dirname(__file__)
ZIP_FILE = os.path.join(_here, 'sample.zip')
ACTUALLY_NOT_ZIP_FILE = os.path.join(_here, 'notazipdespiteitsname.zip')


@pytest.mark.django_db
def test_upload_inbox_upload_task(botomock, fakeuser, settings):

    # Fake an Upload object
    upload = Upload.objects.create(
        user=fakeuser,
        filename='sample.zip',
        bucket_name='mybucket',
        inbox_key='inbox/sample.zip',
        bucket_endpoint_url='http://s4.example.com',
        bucket_region='eu-south-1',
        size=123456,
    )

    # Create a file object that is not a file. That way it can be
    # re-used and not closed leaving an empty file pointer.
    zip_body = BytesIO()
    with open(ZIP_FILE, 'rb') as f:
        zip_body.write(f.read())
    zip_body.seek(0)

    def mock_api_call(self, operation_name, api_params):
        assert api_params['Bucket'] == 'mybucket'  # always the same
        if (
            operation_name == 'HeadObject' and
            api_params['Key'] == 'inbox/sample.zip'
        ):
            return {
                'ContentLength': 123456,
            }

        if (
            operation_name == 'GetObject' and
            api_params['Key'] == 'inbox/sample.zip'
        ):
            return {
                'Body': zip_body,
                'ContentLength': 123456,
            }

        if (
            operation_name == 'HeadObject' and
            api_params['Key'] == 'v0/south-africa-flag.jpeg'
        ):
            # Pretend that we have seen this before and its previous
            # size was 1000.
            return {
                'ContentLength': 1000,
            }

        if (
            operation_name == 'HeadObject' and
            api_params['Key'] == 'v0/xpcshell.sym'
        ):
            # Pretend we've never seen this before
            parsed_response = {
                'Error': {'Code': '404', 'Message': 'Not found'},
            }
            raise ClientError(parsed_response, operation_name)

        if (
            operation_name == 'PutObject' and
            api_params['Key'] == 'v0/south-africa-flag.jpeg'
        ):
            assert 'ContentEncoding' not in api_params
            assert 'ContentType' not in api_params
            content = api_params['Body'].read()
            assert isinstance(content, bytes)
            # based on `unzip -l tests/sample.zip` knowledge
            assert len(content) == 69183

            # ...pretend to actually upload it.
            return {
                # Should there be anything here?
            }
        if (
            operation_name == 'PutObject' and
            api_params['Key'] == 'v0/xpcshell.sym'
        ):
            # Because .sym is in settings.COMPRESS_EXTENSIONS
            assert api_params['ContentEncoding'] == 'gzip'
            # Because .sym is in settings.MIME_OVERRIDES
            assert api_params['ContentType'] == 'text/plain'
            body = api_params['Body'].read()
            assert isinstance(body, bytes)
            # If you look at the fixture 'sample.zip', which is used in
            # these tests you'll see that the file 'xpcshell.sym' is
            # 1156 originally. But we asser that it's now *less* because
            # it should have been gzipped.
            assert len(body) < 1156
            original_content = gzip.decompress(body)
            assert len(original_content) == 1156

            # ...pretend to actually upload it.
            return {}

        if operation_name == 'DeleteObject':
            assert api_params['Key'] == 'inbox/sample.zip'
            # pretend we delete the file
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call):
        upload_inbox_upload(upload.pk)

    # Reload the Upload object
    upload.refresh_from_db()
    assert upload.completed_at

    assert FileUpload.objects.all().count() == 2
    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name='mybucket',
        key='v0/south-africa-flag.jpeg',
        compressed=False,
        update=True,
        size=69183,  # based on `unzip -l tests/sample.zip` knowledge
    )
    assert file_upload.completed_at

    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name='mybucket',
        key='v0/xpcshell.sym',
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that
        # it's been compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )


@pytest.mark.django_db
def test_upload_inbox_upload_task_nothing(botomock, fakeuser, settings):
    """What happens if you try to upload a .zip and every file within
    is exactly already uploaded."""

    # Fake an Upload object
    upload = Upload.objects.create(
        user=fakeuser,
        filename='sample.zip',
        bucket_name='mybucket',
        inbox_key='inbox/sample.zip',
        size=123456,
    )

    # Create a file object that is not a file. That way it can be
    # re-used and not closed leaving an empty file pointer.
    zip_body = BytesIO()
    with open(ZIP_FILE, 'rb') as f:
        zip_body.write(f.read())
    zip_body.seek(0)

    def mock_api_call(self, operation_name, api_params):
        assert api_params['Bucket'] == 'mybucket'  # always the same
        if (
            operation_name == 'HeadObject' and
            api_params['Key'] == 'inbox/sample.zip'
        ):
            return {
                'ContentLength': 123456,
            }

        if (
            operation_name == 'GetObject' and
            api_params['Key'] == 'inbox/sample.zip'
        ):
            return {
                'Body': zip_body,
                'ContentLength': 123456,
            }

        if (
            operation_name == 'HeadObject' and
            api_params['Key'] == 'v0/south-africa-flag.jpeg'
        ):
            # based on `unzip -l tests/sample.zip` knowledge
            return {
                'ContentLength': 69183,
            }

        if (
            operation_name == 'HeadObject' and
            api_params['Key'] == 'v0/xpcshell.sym'
        ):
            # based on `unzip -l tests/sample.zip` knowledge
            return {
                'ContentLength': 1156,
            }

        if operation_name == 'DeleteObject':
            assert api_params['Key'] == 'inbox/sample.zip'
            # pretend we delete the file
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call):
        upload_inbox_upload(upload.pk)

    # Reload the Upload object
    upload.refresh_from_db()
    assert upload.completed_at

    assert not FileUpload.objects.all().exists()


@pytest.mark.django_db
def test_upload_client_bad_request(fakeuser, client, settings):

    def fake_task(*args):
        raise AssertionError('It should never come to actually running this')

    _mock_function = 'tecken.upload.views.upload_inbox_upload.delay'
    with mock.patch(_mock_function, new=fake_task):

        url = reverse('upload:upload_archive')
        response = client.get(url)
        assert response.status_code == 405

        response = client.post(url)
        assert response.status_code == 403

        token = Token.objects.create(user=fakeuser)
        response = client.post(url, HTTP_AUTH_TOKEN=token.key)
        # will also fail because of lack of permission
        assert response.status_code == 403
        # so let's fix that
        permission, = Permission.objects.filter(codename='add_upload')
        fakeuser.user_permissions.add(permission)

        response = client.post(url, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 400
        error_msg = b'Must be multipart form data with at least one file'
        assert error_msg in response.content

        # Upload an empty file
        empty_fileobject = BytesIO()
        response = client.post(
            url,
            {'myfile.zip': empty_fileobject},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 400
        error_msg = b'File size 0'
        assert error_msg in response.content

        settings.DISALLOWED_SYMBOLS_SNIPPETS = ('xpcshell.sym',)

        with open(ZIP_FILE, 'rb') as f:
            response = client.post(
                url,
                {'file.zip': f},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 400
            error_msg = (
                b"Content of archive file contains the snippet "
                b"'xpcshell.sym' which is not allowed"
            )
            assert error_msg in response.content


@pytest.mark.django_db
def test_upload_client_happy_path(botomock, fakeuser, client):
    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='add_upload')
    fakeuser.user_permissions.add(permission)
    url = reverse('upload:upload_archive')

    # The key name for the inbox file upload contains today's date
    # and a MD5 hash of its content based on using 'ZIP_FILE'
    expected_inbox_key_name_regex = re.compile(
        r'inbox/\d{4}-\d{2}-\d{2}/[a-f0-9]{12}/(\w+)\.zip'
    )

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'mybucket'
        if operation_name == 'HeadBucket':
            # yep, bucket exists
            return {}

        if (
            operation_name == 'PutObject' and
            expected_inbox_key_name_regex.findall(api_params['Key'])
        ):
            content = api_params['Body'].read()
            assert isinstance(content, bytes)
            # based on `ls -l tests/sample.zip` knowledge
            assert len(content) == 69519

            # ...pretend to actually upload it.
            return {
                # Should there be anything here?
            }

        raise NotImplementedError((operation_name, api_params))

    task_arguments = []

    def fake_task(upload_id):
        task_arguments.append(upload_id)

    _mock_function = 'tecken.upload.views.upload_inbox_upload.delay'
    with mock.patch(_mock_function, new=fake_task):
        with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
            response = client.post(
                url,
                {'file.zip': f},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 201

            assert task_arguments
            upload = Upload.objects.get(id=task_arguments[0])
            assert upload.user == fakeuser
            assert expected_inbox_key_name_regex.findall(upload.inbox_key)
            assert upload.filename == 'file.zip'
            assert not upload.completed_at
            # based on `ls -l tests/sample.zip` knowledge
            assert upload.size == 69519


@pytest.mark.django_db
def test_upload_client_unrecognized_bucket(botomock, fakeuser, client):
    """The upload view raises an error if you try to upload into a bucket
    that doesn't exist."""
    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='add_upload')
    fakeuser.user_permissions.add(permission)
    url = reverse('upload:upload_archive')

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'mybucket'
        if operation_name == 'HeadBucket':
            parsed_response = {
                'Error': {'Code': '404', 'Message': 'Not found'},
            }
            raise ClientError(parsed_response, operation_name)

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
        with pytest.raises(ImproperlyConfigured):
            client.post(
                url,
                {'file.zip': f},
                HTTP_AUTH_TOKEN=token.key,
            )


def test_get_bucket_info(settings):

    class FakeUser:
        def __init__(self, email):
            self.email = email

    user = FakeUser('peterbe@example.com')

    settings.UPLOAD_DEFAULT_URL = 'https://s3.amazonaws.com/some-bucket'
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == 'some-bucket'
    assert bucket_info.endpoint_url is None
    assert bucket_info.region is None

    settings.UPLOAD_DEFAULT_URL = (
        'https://s3-us-north-2.amazonaws.com/some-bucket'
    )
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == 'some-bucket'
    assert bucket_info.endpoint_url is None
    assert bucket_info.region == 'us-north-2'

    settings.UPLOAD_DEFAULT_URL = 'http://s3.example.com/buck/prefix'
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == 'buck'
    assert bucket_info.endpoint_url == 'http://s3.example.com'
    assert bucket_info.region is None


def test_get_bucket_info_exceptions(settings):

    class FakeUser:
        def __init__(self, email):
            self.email = email

    settings.UPLOAD_DEFAULT_URL = 'https://s3.amazonaws.com/buck'
    settings.UPLOAD_URL_EXCEPTIONS = {
        'peterbe@example.com': 'https://s3.amazonaws.com/differenting',
        't*@example.com': 'https://s3.amazonaws.com/excepty',
    }

    user = FakeUser('Peterbe@example.com')
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == 'differenting'

    user = FakeUser('Tucker@example.com')
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == 'excepty'
