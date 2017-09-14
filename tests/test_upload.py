# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import gzip
import os
import re
import shutil
from io import BytesIO

import pytest
import mock
from botocore.exceptions import ClientError, EndpointConnectionError
from requests.exceptions import ConnectionError
from markus import TIMING, INCR

from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.db.models import F
from django.utils import timezone

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload
from tecken.upload import tasks
from tecken.upload.tasks import upload_inbox_upload
from tecken.base.symboldownloader import SymbolDownloader
from tecken.boto_extra import OwnEndpointConnectionError, OwnClientError
from tecken.upload.views import get_bucket_info
from tecken.upload.forms import UploadByDownloadForm
from tecken.upload.utils import get_archive_members


_here = os.path.dirname(__file__)
ZIP_FILE = os.path.join(_here, 'sample.zip')
TGZ_FILE = os.path.join(_here, 'sample.tgz')
TARGZ_FILE = os.path.join(_here, 'sample.tar.gz')
INVALID_ZIP_FILE = os.path.join(_here, 'invalid.zip')
ACTUALLY_NOT_ZIP_FILE = os.path.join(_here, 'notazipdespiteitsname.zip')


def test_get_archive_members():
    with open(TGZ_FILE, 'rb') as f:
        file_listing, = get_archive_members(f, f.name)
        assert file_listing.name == (
            'south-africa-flag/deadbeef/south-africa-flag.jpeg'
        )
        assert file_listing.size == 69183

    with open(TARGZ_FILE, 'rb') as f:
        file_listing, = get_archive_members(f, f.name)
        assert file_listing.name == (
            'south-africa-flag/deadbeef/south-africa-flag.jpeg'
        )
        assert file_listing.size == 69183

    with open(ZIP_FILE, 'rb') as f:
        file_listings = list(get_archive_members(f, f.name))
        # That .zip file has multiple files in it so it's hard to rely
        # on the order.
        assert len(file_listings) == 3
        for file_listing in file_listings:
            assert file_listing.name
            assert file_listing.size


@pytest.mark.django_db
def test_upload_inbox_upload_task(botomock, fakeuser, settings, metricsmock):

    # Fake an Upload object
    inbox_filepath = os.path.join(
        settings.UPLOAD_INBOX_DIRECTORY, 'sample.zip'
    )
    shutil.copyfile(ZIP_FILE, inbox_filepath)
    upload = Upload.objects.create(
        user=fakeuser,
        filename='sample.zip',
        bucket_name='mybucket',
        inbox_filepath=inbox_filepath,
        bucket_endpoint_url='http://s4.example.com',
        bucket_region='eu-south-1',
        size=123456,
    )

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
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
        ):
            # Pretend that we have this in S3 and its previous
            # size was 1000.
            return {'Contents': [
                {
                    'Key': (
                        'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
                    ),
                    'Size': 1000,
                }
            ]}

        if (
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
        ):
            # Pretend we don't have this in S3 at all
            return {}

        if (
            operation_name == 'PutObject' and
            api_params['Key'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
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
            api_params['Key'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
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

    assert not os.path.isfile(inbox_filepath)

    # Reload the Upload object
    upload.refresh_from_db()
    assert upload.completed_at
    assert upload.skipped_keys is None
    assert upload.ignored_keys == ['build-symbols.txt']
    assert upload.attempts == 1

    assert FileUpload.objects.all().count() == 2
    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name='mybucket',
        key='v0/south-africa-flag/deadbeef/south-africa-flag.jpeg',
        compressed=False,
        update=True,
        size=69183,  # based on `unzip -l tests/sample.zip` knowledge
    )
    assert file_upload.completed_at

    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name='mybucket',
        key='v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym',
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that
        # it's been compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )

    # Check that markus caught timings of the individual file processing
    records = metricsmock.get_records()
    assert len(records) == 4
    assert records[0][0] == TIMING
    assert records[1][0] == INCR
    assert records[2][0] == TIMING
    assert records[3][0] == INCR


@pytest.mark.django_db
def test_upload_inbox_upload_task_with_inbox_key(
    botomock,
    fakeuser,
    settings,
    metricsmock
):
    """This test is the same as test_upload_inbox_upload_task but this
    time we use 'inbox_key' (ie. using S3 as the inbox file storage)
    instead of 'inbox_filepath'.

    This test can be deleted when we know that using disk as the conduit
    really works."""

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
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
        ):
            # Pretend that we have this in S3 and its previous
            # size was 1000.
            return {'Contents': [
                {
                    'Key': (
                        'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
                    ),
                    'Size': 1000,
                }
            ]}

        if (
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
        ):
            # Pretend we don't have this in S3 at all
            return {}

        if (
            operation_name == 'PutObject' and
            api_params['Key'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
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
            api_params['Key'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
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
    assert upload.skipped_keys is None
    assert upload.ignored_keys == ['build-symbols.txt']
    assert upload.attempts == 1

    assert FileUpload.objects.all().count() == 2
    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name='mybucket',
        key='v0/south-africa-flag/deadbeef/south-africa-flag.jpeg',
        compressed=False,
        update=True,
        size=69183,  # based on `unzip -l tests/sample.zip` knowledge
    )
    assert file_upload.completed_at

    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name='mybucket',
        key='v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym',
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that
        # it's been compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )

    # Check that markus caught timings of the individual file processing
    records = metricsmock.get_records()
    assert len(records) == 4
    assert records[0][0] == TIMING
    assert records[1][0] == INCR
    assert records[2][0] == TIMING
    assert records[3][0] == INCR


@pytest.mark.django_db
def test_upload_inbox_upload_task_with_cache_invalidation(
    botomock,
    fakeuser,
    settings,
    metricsmock,
):
    settings.SYMBOL_URLS = ['https://s3.example.com/mybucket']
    downloader = SymbolDownloader(settings.SYMBOL_URLS)
    tasks.downloader = downloader

    inbox_filepath = os.path.join(
        settings.UPLOAD_INBOX_DIRECTORY, 'sample.zip'
    )
    shutil.copyfile(ZIP_FILE, inbox_filepath)
    upload = Upload.objects.create(
        user=fakeuser,
        filename='sample.zip',
        bucket_name='mybucket',
        inbox_filepath=inbox_filepath,
        bucket_endpoint_url='http://s4.example.com',
        bucket_region='eu-south-1',
        size=123456,
    )

    # A mutable we use to help us distinguish between calls in the mock
    lookups = []

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
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
        ):
            # Pretend that we have this in S3 and its previous
            # size was 1000.
            return {'Contents': [
                {
                    'Key': (
                        'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
                    ),
                    'Size': 1000,
                }
            ]}

        if (
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
        ):
            if not lookups:
                # This is when the SymbolDownloader queries it.
                result = {}
            elif len(lookups) == 1:
                # This is when the upload task queries it.
                result = {}
            else:
                result = {
                    'Contents': [
                        {
                            'Key': api_params['Prefix'],
                            'Size': 100,
                        }
                    ]
                }
            lookups.append(api_params['Prefix'])
            # Pretend we don't have this in S3 at all
            return result

        if (
            operation_name == 'PutObject' and
            api_params['Key'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
        ):
            # ...pretend to actually upload it.
            return {
                # Should there be anything here?
            }
        if (
            operation_name == 'PutObject' and
            api_params['Key'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
        ):
            # ...pretend to actually upload it.
            return {}

        if operation_name == 'DeleteObject':
            # pretend we delete the file
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call):

        # First time.
        assert not downloader.has_symbol(
            'xpcshell.dbg', 'A7D6F1BB18CD4CB48', 'xpcshell.sym'
        )

        # Do the actual upload.
        upload_inbox_upload(upload.pk)

        # Second time.
        # assert downloader.has_symbol(
        assert downloader.has_symbol(
            'xpcshell.dbg', 'A7D6F1BB18CD4CB48', 'xpcshell.sym'
        )

        # This is just basically to make sense of all the crazy mocking.
        assert len(lookups) == 3

    assert not os.path.isfile(inbox_filepath)


@pytest.mark.django_db
def test_upload_inbox_upload_task_retried(botomock, fakeuser, settings):

    # Fake an Upload object
    inbox_filepath = os.path.join(
        settings.UPLOAD_INBOX_DIRECTORY, 'sample.zip'
    )
    shutil.copyfile(ZIP_FILE, inbox_filepath)
    upload = Upload.objects.create(
        user=fakeuser,
        filename='sample.zip',
        bucket_name='mybucket',
        inbox_filepath=inbox_filepath,
        bucket_endpoint_url='http://s4.example.com',
        bucket_region='eu-south-1',
        size=123456,
    )

    calls = []

    def mock_api_call(self, operation_name, api_params):
        assert api_params['Bucket'] == 'mybucket'  # always the same
        call_key = (operation_name, tuple(api_params.items()))
        first_time = call_key not in calls
        second_time = calls.count(call_key) == 1
        calls.append(call_key)

        endpoint_error = EndpointConnectionError(
            endpoint_url='http://example.com'
        )
        if (
            operation_name == 'HeadObject' and
            api_params['Key'] == 'inbox/sample.zip'
        ):
            return {
                'ContentLength': 123456,
            }

        if (
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
        ):
            return {'Contents': [
                {
                    'Key': (
                        'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
                    ),
                    'Size': 1000,
                }
            ]}

        if (
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
        ):
            # Give it grief on the HeadObject op the first time
            if first_time:
                raise endpoint_error
            elif second_time:
                parsed_response = {
                    'Error': {'Code': '500', 'Message': 'Server Error'},
                }
                raise ClientError(parsed_response, operation_name)

            # Pretend we don't have this in S3
            return {}

        if (
            operation_name == 'PutObject' and
            api_params['Key'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
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
            api_params['Key'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
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
        try:
            upload_inbox_upload(upload.pk)
            assert False, "Should have failed"
        except OwnEndpointConnectionError:
            # That should have made some FileUpload objects for this
            # Upload object.
            qs = FileUpload.objects.filter(upload=upload)
            assert qs.count() == 1

            # Simulate what Celery does, which is to simply run this
            # again after a little pause.
            try:
                upload_inbox_upload(upload.pk)
                assert False, "Should have failed the second time too"

            except OwnClientError as exception:
                # That should have made some FileUpload objects for this
                # Upload object.
                qs = FileUpload.objects.filter(upload=upload)
                assert qs.count() == 1

                # Simulate what Celery does, which is to simply run this
                # again after a little pause.
                upload_inbox_upload(upload.pk)

                assert qs.count() == 2
                # also, all of them should be completed
                assert qs.filter(completed_at__isnull=False).count() == 2

    # Reload the Upload object
    upload.refresh_from_db()
    assert upload.completed_at
    assert upload.skipped_keys is None

    assert not os.path.isfile(inbox_filepath)


@pytest.mark.django_db
def test_upload_inbox_upload_task_nothing(
    botomock,
    fakeuser,
    settings,
    metricsmock
):
    """What happens if you try to upload a .zip and every file within
    is exactly already uploaded."""

    # Fake an Upload object
    inbox_filepath = os.path.join(
        settings.UPLOAD_INBOX_DIRECTORY, 'sample.zip'
    )
    shutil.copyfile(ZIP_FILE, inbox_filepath)
    upload = Upload.objects.create(
        user=fakeuser,
        filename='sample.zip',
        bucket_name='mybucket',
        inbox_filepath=inbox_filepath,
        size=123456,
    )

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
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
        ):
            return {'Contents': [
                {
                    'Key': (
                        'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
                    ),
                    # based on `unzip -l tests/sample.zip` knowledge
                    'Size': 69183,
                }
            ]}

        if (
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
        ):
            return {'Contents': [
                {
                    'Key': (
                        'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
                    ),
                    # based on `unzip -l tests/sample.zip` knowledge
                    'Size': 488,
                }
            ]}

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
    assert len(upload.skipped_keys) == 2
    assert metricsmock.has_record(
        INCR, 'tecken.upload_file_upload_skip', 1, None
    )
    assert not FileUpload.objects.all().exists()

    assert not os.path.isfile(inbox_filepath)


@pytest.mark.django_db
def test_upload_inbox_upload_task_one_uploaded_one_skipped(
    botomock,
    fakeuser,
    settings,
    metricsmock,
):
    """Two incoming files. One was already there and the same size."""

    inbox_filepath = os.path.join(
        settings.UPLOAD_INBOX_DIRECTORY, 'sample.zip'
    )
    shutil.copyfile(ZIP_FILE, inbox_filepath)
    # Fake an Upload object
    upload = Upload.objects.create(
        user=fakeuser,
        filename='sample.zip',
        bucket_name='mybucket',
        inbox_filepath=inbox_filepath,
        size=123456,
    )

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
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
            )
        ):
            return {'Contents': [
                {
                    'Key': (
                        'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
                    ),
                    # based on `unzip -l tests/sample.zip` knowledge
                    'Size': 69183,
                }
            ]}

        if (
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
        ):
            # Not found at all
            return {}

        if (
            operation_name == 'PutObject' and
            api_params['Key'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
        ):
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
    assert len(upload.skipped_keys) == 1
    assert metricsmock.has_record(
        INCR, 'tecken.upload_file_upload_skip', 1, None
    )
    assert metricsmock.has_record(
        INCR, 'tecken.upload_file_upload_upload', 1, None
    )
    assert FileUpload.objects.all().count() == 1

    assert not os.path.isfile(inbox_filepath)


@pytest.mark.django_db
def test_upload_client_bad_request(fakeuser, client, settings):

    def fake_task(*args):
        raise AssertionError('It should never come to actually running this')

    _mock_function = 'tecken.upload.views.upload_inbox_upload.delay'
    with mock.patch(_mock_function, new=fake_task):

        url = reverse('upload:upload_archive')
        response = client.get(url)
        assert response.status_code == 405
        error_msg = 'Method Not Allowed (GET): /upload/'
        assert response.json()['error'] == error_msg

        response = client.post(url)
        assert response.status_code == 403
        error_msg = 'This requires an Auth-Token to authenticate the request'
        assert response.json()['error'] == error_msg

        token = Token.objects.create(user=fakeuser)
        response = client.post(url, HTTP_AUTH_TOKEN=token.key)
        # will also fail because of lack of permission
        assert response.status_code == 403
        assert response.json()['error'] == 'Forbidden'

        # so let's fix that
        permission, = Permission.objects.filter(codename='upload_symbols')
        token.permissions.add(permission)

        response = client.post(url, HTTP_AUTH_TOKEN=token.key)
        assert response.status_code == 400
        error_msg = 'Must be multipart form data with at least one file'
        assert response.json()['error'] == error_msg

        # Upload an empty file
        empty_fileobject = BytesIO()
        response = client.post(
            url,
            {'myfile.zip': empty_fileobject},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 400
        assert response.json()['error'] == 'File size 0'

        # Unrecognized file extension
        with open(ZIP_FILE, 'rb') as f:
            response = client.post(
                url,
                {'myfile.rar': f},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 400
            assert response.json()['error'] == (
                'Unrecognized archive file extension ".rar"'
            )

        settings.DISALLOWED_SYMBOLS_SNIPPETS = ('xpcshell.sym',)

        with open(ZIP_FILE, 'rb') as f:
            response = client.post(
                url,
                {'file.zip': f},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 400
            error_msg = (
                "Content of archive file contains the snippet "
                "'xpcshell.sym' which is not allowed"
            )
            assert response.json()['error'] == error_msg

        # Undo that setting override
        settings.DISALLOWED_SYMBOLS_SNIPPETS = ('nothing',)

        # Now upload a file that doesn't have the right filename patterns
        with open(INVALID_ZIP_FILE, 'rb') as f:
            response = client.post(
                url,
                {'file.zip': f},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 400
            error_msg = (
                'Unrecognized file pattern. Should only be '
                '<module>/<hex>/<file> or <name>-symbols.txt and nothing else.'
            )
            assert response.json()['error'] == error_msg

        # Now upload a file that isn't a zip file
        with open(ACTUALLY_NOT_ZIP_FILE, 'rb') as f:
            response = client.post(
                url,
                {'file.zip': f},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 400
            error_msg = 'File is not a zip file'
            assert response.json()['error'] == error_msg


@pytest.mark.django_db
def test_upload_client_happy_path(botomock, fakeuser, client):
    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    # The key name for the inbox file upload contains today's date
    # and a MD5 hash of its content based on using 'ZIP_FILE'
    expected_inbox_key_name_regex = re.compile(
        r'inbox/\d{4}-\d{2}-\d{2}/[a-f0-9]{12}/(\w+)\.zip'
    )

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
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
            assert len(content) == 69812

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
            assert upload.inbox_key is None
            assert expected_inbox_key_name_regex.findall(upload.inbox_filepath)
            assert upload.filename == 'file.zip'
            assert not upload.completed_at
            # based on `ls -l tests/sample.zip` knowledge
            assert upload.size == 69812


@pytest.mark.django_db
def test_upload_client_reattempt(botomock, fakeuser, client, clear_cache):
    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    # The key name for the inbox file upload contains today's date
    # and a MD5 hash of its content based on using 'ZIP_FILE'
    expected_inbox_key_name_regex = re.compile(
        r'inbox/\d{4}-\d{2}-\d{2}/[a-f0-9]{12}/(\w+)\.zip'
    )

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
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
            assert len(content) == 69812

            # ...pretend to actually upload it.
            return {
                # Should there be anything here?
            }

        raise NotImplementedError((operation_name, api_params))

    task_arguments = []

    # Pretend this upload is old and stuck
    old_upload = Upload.objects.create(
        user=fakeuser,
        filename='sample.zip',
        bucket_name='mybucket',
        inbox_key='inbox/01/sample.zip',
        bucket_endpoint_url='http://s4.example.com',
        bucket_region='eu-south-1',
        size=123456,
        attempts=1,
    )
    # Have to manually edit because 'created_at' is auto_now_add=True
    old_upload.created_at = (
        timezone.now() - datetime.timedelta(days=1)
    )
    old_upload.save()

    def fake_task(upload_id):
        task_arguments.append(upload_id)
        # pretend we successfully process it
        Upload.objects.filter(id=upload_id).update(
            attempts=F('attempts') + 1,
            completed_at=timezone.now()
        )

    _mock_function = 'tecken.upload.views.upload_inbox_upload.delay'
    with mock.patch(_mock_function, new=fake_task):
        with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
            response = client.post(
                url,
                {'file.zip': f},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 201

            assert len(task_arguments) == 2
            upload = Upload.objects.get(id=task_arguments[0])
            assert upload.inbox_key is None
            assert upload.inbox_filepath
            assert expected_inbox_key_name_regex.findall(upload.inbox_filepath)
            assert upload.completed_at
            assert upload.attempts == 1

            old_upload.refresh_from_db()
            assert old_upload.completed_at
            assert old_upload.attempts == 2


@pytest.mark.django_db
def test_upload_client_unrecognized_bucket(botomock, fakeuser, client):
    """The upload view raises an error if you try to upload into a bucket
    that doesn't exist."""
    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
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
        'https://s3-eu-west-2.amazonaws.com/some-bucket'
    )
    bucket_info = get_bucket_info(user)
    assert bucket_info.name == 'some-bucket'
    assert bucket_info.endpoint_url is None
    assert bucket_info.region == 'eu-west-2'

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


@pytest.mark.django_db
def test_upload_client_by_download_url(
    botomock,
    fakeuser,
    client,
    settings,
    requestsmock,
):

    requestsmock.head(
        'https://whitelisted.example.com/symbols.zip',
        text='Found',
        status_code=302,
        headers={
            'Location': 'https://download.example.com/symbols.zip',
        }
    )
    requestsmock.head(
        'https://whitelisted.example.com/bad.zip',
        text='Found',
        status_code=302,
        headers={
            'Location': 'https://bad.example.com/symbols.zip',
        }
    )

    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = [
        'whitelisted.example.com',
        'download.example.com',
    ]
    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    # The key name for the inbox file upload contains today's date
    # and a MD5 hash of its content based on using 'ZIP_FILE'
    expected_inbox_key_name_regex = re.compile(
        r'inbox/\d{4}-\d{2}-\d{2}/[a-f0-9]{12}/(\w+)\.zip'
    )

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
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
            assert len(content) == 69812

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
                data={'url': 'http://example.com/symbols.zip'},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 400
            assert response.json()['error'] == 'Insecure URL'

            response = client.post(
                url,
                data={'url': 'https://notwhitelisted.example.com/symbols.zip'},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 400
            assert response.json()['error'] == (
                "Not an allowed domain ('notwhitelisted.example.com') to "
                "download from"
            )

            # More tricky, a URL that when redirecting, redirects
            # somewhere "bad".
            response = client.post(
                url,
                data={'url': 'https://whitelisted.example.com/bad.zip'},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 400
            assert response.json()['error'] == (
                "Not an allowed domain ('bad.example.com') to "
                "download from"
            )

            # Lastly, the happy path
            zip_file_content = f.read()
            requestsmock.head(
                'https://download.example.com/symbols.zip',
                content=b'',
                status_code=200,
                headers={
                    'Content-Length': str(len(zip_file_content)),
                }
            )
            requestsmock.get(
                'https://download.example.com/symbols.zip',
                content=zip_file_content,
                status_code=200,
            )
            response = client.post(
                url,
                data={'url': 'https://whitelisted.example.com/symbols.zip'},
                HTTP_AUTH_TOKEN=token.key,
            )
            assert response.status_code == 201
            assert response.json()['upload']['download_url'] == (
                'https://download.example.com/symbols.zip'
            )
            upload = Upload.objects.get(id=task_arguments[0])
            assert upload.user == fakeuser
            assert upload.download_url == (
                'https://download.example.com/symbols.zip'
            )
            assert upload.inbox_key is None
            assert upload.inbox_filepath
            assert expected_inbox_key_name_regex.findall(upload.inbox_filepath)
            assert upload.filename == 'symbols.zip'
            assert not upload.completed_at
            # based on `ls -l tests/sample.zip` knowledge
            assert upload.size == 69812


def test_upload_by_download_form_happy_path(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = ['whitelisted.example.com']

    requestsmock.head(
        'https://whitelisted.example.com/symbols.zip',
        content=b'content',
        status_code=200,
        headers={
            'Content-Length': '1234',
        }
    )

    form = UploadByDownloadForm({
        'url': 'https://whitelisted.example.com/symbols.zip',
    })
    assert form.is_valid()
    assert form.cleaned_data['url'] == (
        'https://whitelisted.example.com/symbols.zip'
    )
    assert form.cleaned_data['upload']['name'] == 'symbols.zip'
    assert form.cleaned_data['upload']['size'] == 1234


def test_upload_by_download_form_connectionerrors(requestsmock, settings):
    settings.ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS = [
        'whitelisted.example.com',
        'download.example.com',
    ]

    requestsmock.head(
        'https://whitelisted.example.com/symbols.zip',
        exc=ConnectionError,
    )

    form = UploadByDownloadForm({
        'url': 'https://whitelisted.example.com/symbols.zip',
    })
    assert not form.is_valid()
    validation_errors, = form.errors.as_data().values()
    assert validation_errors[0].message == (
        'ConnectionError trying to open '
        'https://whitelisted.example.com/symbols.zip'
    )

    # Suppose the HEAD request goes to another URL which eventually
    # raises a ConnectionError.

    requestsmock.head(
        'https://whitelisted.example.com/redirect.zip',
        text='Found',
        status_code=302,
        headers={
            'Location': 'https://download.example.com/busted.zip'
        }
    )
    requestsmock.head(
        'https://download.example.com/busted.zip',
        exc=ConnectionError,
    )
    form = UploadByDownloadForm({
        'url': 'https://whitelisted.example.com/redirect.zip',
    })
    assert not form.is_valid()
    validation_errors, = form.errors.as_data().values()
    assert validation_errors[0].message == (
        'ConnectionError trying to open '
        'https://download.example.com/busted.zip'
    )

    # Suppose the URL simply is not found.
    requestsmock.head(
        'https://whitelisted.example.com/404.zip',
        text='Not Found',
        status_code=404,
    )
    form = UploadByDownloadForm({
        'url': 'https://whitelisted.example.com/404.zip',
    })
    assert not form.is_valid()
    validation_errors, = form.errors.as_data().values()
    assert validation_errors[0].message == (
        "https://whitelisted.example.com/404.zip can't be found (404)"
    )
