# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import gzip
import os
import zipfile
import tempfile
from io import BytesIO

import pytest
from botocore.exceptions import ClientError
from requests.exceptions import ConnectionError

from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured

from tecken.tokens.models import Token
from tecken.upload.models import Upload, FileUpload
from tecken.upload import utils
from tecken.base.symboldownloader import SymbolDownloader
from tecken.upload.views import get_bucket_info
from tecken.upload.forms import UploadByDownloadForm
from tecken.upload.utils import (
    get_archive_members,
    key_existing_size,
    should_compressed_key,
    get_key_content_type,
)


_here = os.path.dirname(__file__)
ZIP_FILE = os.path.join(_here, 'sample.zip')
INVALID_ZIP_FILE = os.path.join(_here, 'invalid.zip')
ACTUALLY_NOT_ZIP_FILE = os.path.join(_here, 'notazipdespiteitsname.zip')


class FakeUser:
    def __init__(self, email):
        self.email = email


def test_get_archive_members():
    with open(ZIP_FILE, 'rb') as f, tempfile.TemporaryDirectory() as tmpdir:
        zf = zipfile.ZipFile(f)
        zf.extractall(tmpdir)
        file_listings = list(get_archive_members(tmpdir))
        # That .zip file has multiple files in it so it's hard to rely
        # on the order.
        assert len(file_listings) == 3
        for file_listing in file_listings:
            assert file_listing.path
            assert os.path.isfile(file_listing.path)
            assert file_listing.name
            assert not file_listing.name.startswith('/')
            assert file_listing.size
            assert file_listing.size == os.stat(file_listing.path).st_size


def test_should_compressed_key(settings):
    settings.COMPRESS_EXTENSIONS = ['bar']
    assert should_compressed_key('foo.bar')
    assert should_compressed_key('foo.BAR')
    assert not should_compressed_key('foo.exe')


def test_get_key_content_type(settings):
    settings.MIME_OVERRIDES = {
        'html': 'text/html',
    }
    assert get_key_content_type('foo.bar') is None
    assert get_key_content_type('foo.html') == 'text/html'
    assert get_key_content_type('foo.HTML') == 'text/html'


@pytest.mark.django_db(transaction=True)  # needed because of concurrency
def test_upload_archive_happy_path(client, botomock, fakeuser, metricsmock):

    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
        if operation_name == 'HeadBucket':
            # yep, bucket exists
            return {}

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

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
        response = client.post(
            url,
            {'file.zip': f},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 201

        upload, = Upload.objects.all()
        assert upload.user == fakeuser
        assert upload.filename == 'file.zip'
        assert upload.completed_at
        # Based on `ls -l tests/sample.zip` knowledge
        assert upload.size == 69812
        # This is predictable and shouldn't change unless the fixture
        # file used changes.
        assert upload.content_hash == 'f7382729695218a7fa003d63246b26'
        assert upload.bucket_name == 'private'
        assert upload.bucket_region is None
        assert upload.bucket_endpoint_url == 'https://s3.example.com'
        assert upload.skipped_keys is None
        assert upload.ignored_keys == ['build-symbols.txt']

    assert FileUpload.objects.all().count() == 2
    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name='private',
        key='v0/south-africa-flag/deadbeef/south-africa-flag.jpeg',
        compressed=False,
        update=True,
        size=69183,  # based on `unzip -l tests/sample.zip` knowledge
    )
    assert file_upload.completed_at

    file_upload = FileUpload.objects.get(
        upload=upload,
        bucket_name='private',
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
    assert len(records) == 10
    # It's impossible to predict, the order of some metrics records
    # because of the use of ThreadPoolExecutor. So we can't look at them
    # in the exact order.
    all_tags = [x[1] for x in records]
    assert all_tags.count('tecken.upload_file_exists') == 2
    assert all_tags.count('tecken.upload_gzip_payload') == 1  # only 1 .sym
    assert all_tags.count('tecken.upload_put_object') == 2
    assert all_tags.count('tecken.upload_file_upload_upload') == 2
    assert all_tags.count('tecken.upload_file_upload') == 2
    assert all_tags[-1] == 'tecken.upload_archive'


@pytest.mark.django_db(transaction=True)
def test_upload_archive_one_uploaded_one_skipped(
    client,
    botomock,
    fakeuser,
    metricsmock
):

    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
        if operation_name == 'HeadBucket':
            # yep, bucket exists
            return {}

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

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
        response = client.post(
            url,
            {'file.zip': f},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 201

        upload, = Upload.objects.all()
        assert upload.user == fakeuser
        # assert upload.inbox_key is None
        # assert expected_inbox_key_name_regex.findall(upload.inbox_filepath)
        assert upload.filename == 'file.zip'
        assert upload.completed_at
        # based on `ls -l tests/sample.zip` knowledge
        assert upload.size == 69812
        assert upload.bucket_name == 'private'
        assert upload.bucket_region is None
        assert upload.bucket_endpoint_url == 'https://s3.example.com'
        assert upload.skipped_keys == [
            'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg'
        ]
        assert upload.ignored_keys == ['build-symbols.txt']

    assert FileUpload.objects.all().count() == 1
    assert FileUpload.objects.get(
        upload=upload,
        bucket_name='private',
        key='v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym',
        compressed=True,
        update=False,
        # Based on `unzip -l tests/sample.zip` knowledge, but note that
        # it's been compressed.
        size__lt=1156,
        completed_at__isnull=False,
    )


def test_key_existing_size_caching(botomock, metricsmock):

    user = FakeUser('peterbe@example.com')
    bucket_info = get_bucket_info(user)

    sizes_returned = []
    lookups = []

    def mock_api_call(self, operation_name, api_params):
        lookups.append((operation_name, api_params))

        if (
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == 'filename'
        ):
            size = 1234
            if sizes_returned:
                size = 6789
            result = {'Contents': [
                {
                    'Key': (
                        'filename'
                    ),
                    'Size': size,
                }
            ]}
            sizes_returned.append(size)
            return result

        raise NotImplementedError

    s3_client = bucket_info.s3_client
    with botomock(mock_api_call):
        size = key_existing_size(s3_client, 'mybucket', 'filename')
        assert size == 1234
        assert len(lookups) == 1

        size = key_existing_size(s3_client, 'mybucket', 'filename')
        assert size == 1234
        assert len(lookups) == 1

        key_existing_size.invalidate(s3_client, 'mybucket', 'filename')
        size = key_existing_size(s3_client, 'mybucket', 'filename')
        assert size == 6789
        assert len(lookups) == 2


def test_key_existing_size_caching_not_found(botomock, metricsmock):

    user = FakeUser('peterbe@example.com')
    bucket_info = get_bucket_info(user)

    # sizes_returned = []
    lookups = []

    def mock_api_call(self, operation_name, api_params):
        lookups.append((operation_name, api_params))

        if (
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == 'filename'
        ):
            return {}

        raise NotImplementedError

    s3_client = bucket_info.s3_client
    with botomock(mock_api_call):
        size = key_existing_size(s3_client, 'mybucket', 'filename')
        assert size is 0
        assert len(lookups) == 1

        size = key_existing_size(s3_client, 'mybucket', 'filename')
        assert size is 0
        assert len(lookups) == 1

        key_existing_size.invalidate(s3_client, 'mybucket', 'filename')
        size = key_existing_size(s3_client, 'mybucket', 'filename')
        assert size is 0
        assert len(lookups) == 2


@pytest.mark.django_db(transaction=True)
def test_upload_archive_key_lookup_cached(
    client,
    botomock,
    fakeuser,
    metricsmock
):

    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    lookups = []

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
        if operation_name == 'HeadBucket':
            # yep, bucket exists
            return {}

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
            # Saying the size is 100 will cause the code to think the
            # symbol file *is different* so it'll proceed to upload it.
            size = 100
            if lookups:
                # If this is the second time, return the right size.
                size = 501
            result = {
                'Contents': [
                    {
                        'Key': api_params['Prefix'],
                        'Size': size,
                    }
                ]
            }
            lookups.append(size)
            return result

        if (
            operation_name == 'PutObject' and
            api_params['Key'] == (
                'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym'
            )
        ):
            # ...pretend to actually upload it.
            return {}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
        response = client.post(
            url,
            {'file.zip': f},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 201

        assert Upload.objects.all().count() == 1
        assert FileUpload.objects.all().count() == 1

    # Upload the same file again. This time some of the S3 ListObjectsV2
    # operations should benefit from a cache.
    with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
        response = client.post(
            url,
            {'file.zip': f},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 201

        assert Upload.objects.all().count() == 2
        assert FileUpload.objects.all().count() == 1
        assert len(lookups) == 2

    # Upload the same file again. This time some of the S3 ListObjectsV2
    # operations should benefit from a cache.
    with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
        response = client.post(
            url,
            {'file.zip': f},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 201

        assert Upload.objects.all().count() == 3
        assert FileUpload.objects.all().count() == 1
        # This time it doesn't need to look up the size a third time
        assert len(lookups) == 2


@pytest.mark.django_db(transaction=True)
def test_upload_archive_one_uploaded_one_errored(
    client,
    botomock,
    fakeuser,
    metricsmock
):

    class AnyUnrecognizedError(Exception):
        """Doesn't matter much what the exception is. What matters is that
        it happens during a boto call."""

    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
        if operation_name == 'HeadBucket':
            # yep, bucket exists
            return {}

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
            raise AnyUnrecognizedError('stop!')

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
        with pytest.raises(AnyUnrecognizedError):
            client.post(
                url,
                {'file.zip': f},
                HTTP_AUTH_TOKEN=token.key,
            )

        upload, = Upload.objects.all()
        assert upload.user == fakeuser
        assert not upload.completed_at

    assert FileUpload.objects.all().count() == 1
    assert FileUpload.objects.get(
        upload=upload,
        key='v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym',
    )


@pytest.mark.django_db(transaction=True)
def test_upload_archive_with_cache_invalidation(
    client,
    botomock,
    fakeuser,
    metricsmock,
    settings
):

    settings.SYMBOL_URLS = ['https://s3.example.com/mybucket']
    settings.UPLOAD_DEFAULT_URL = 'https://s3.example.com/mybucket'
    downloader = SymbolDownloader(settings.SYMBOL_URLS)
    utils.downloader = downloader

    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    # A mutable we use to help us distinguish between calls in the mock
    lookups = []

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'mybucket'
        if operation_name == 'HeadBucket':
            # yep, bucket exists
            return {}

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

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:

        assert not downloader.has_symbol(
            'xpcshell.dbg', 'A7D6F1BB18CD4CB48', 'xpcshell.sym'
        )

        response = client.post(
            url,
            {'file.zip': f},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 201

        # Second time.
        assert downloader.has_symbol(
            'xpcshell.dbg', 'A7D6F1BB18CD4CB48', 'xpcshell.sym'
        )

        # This is just basically to make sense of all the crazy mocking.
        assert len(lookups) == 3


@pytest.mark.django_db(transaction=True)
def test_upload_archive_both_skipped(
    client,
    botomock,
    fakeuser,
    metricsmock
):

    token = Token.objects.create(user=fakeuser)
    permission, = Permission.objects.filter(codename='upload_symbols')
    token.permissions.add(permission)
    url = reverse('upload:upload_archive')

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
        if operation_name == 'HeadBucket':
            # yep, bucket exists
            return {}

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
                    'Size': 501,
                }
            ]}

        raise NotImplementedError((operation_name, api_params))

    with botomock(mock_api_call), open(ZIP_FILE, 'rb') as f:
        response = client.post(
            url,
            {'file.zip': f},
            HTTP_AUTH_TOKEN=token.key,
        )
        assert response.status_code == 201

        upload, = Upload.objects.all()
        assert upload.user == fakeuser
        # assert upload.inbox_key is None
        # assert expected_inbox_key_name_regex.findall(upload.inbox_filepath)
        assert upload.filename == 'file.zip'
        assert upload.completed_at
        # based on `ls -l tests/sample.zip` knowledge
        assert upload.size == 69812
        assert upload.bucket_name == 'private'
        assert upload.bucket_region is None
        assert upload.bucket_endpoint_url == 'https://s3.example.com'
        # Order isn't predictable so compare using sets.
        assert set(upload.skipped_keys) == set([
            'v0/south-africa-flag/deadbeef/south-africa-flag.jpeg',
            'v0/xpcshell.dbg/A7D6F1BB18CD4CB48/xpcshell.sym',
        ])
        assert upload.ignored_keys == ['build-symbols.txt']

    assert not FileUpload.objects.all().exists()


@pytest.mark.django_db(transaction=True)
def test_upload_archive_by_url(
    client,
    botomock,
    fakeuser,
    metricsmock,
    settings,
    requestsmock
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

    def mock_api_call(self, operation_name, api_params):
        # This comes for the setting UPLOAD_DEFAULT_URL specifically
        # for tests.
        assert api_params['Bucket'] == 'private'
        if operation_name == 'HeadBucket':
            # yep, bucket exists
            return {}

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

        raise NotImplementedError((operation_name, api_params))

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
        print(response.json())
        assert response.status_code == 201
        assert response.json()['upload']['download_url'] == (
            'https://download.example.com/symbols.zip'
        )

        upload, = Upload.objects.all()
        assert upload.download_url
        assert upload.user == fakeuser
        assert upload.filename == 'symbols.zip'
        assert upload.completed_at

    assert FileUpload.objects.filter(upload=upload).count() == 2


@pytest.mark.django_db
def test_upload_client_bad_request(fakeuser, client, settings):

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
    assert response.json()['error'] == 'File is not a zip file'

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


def test_UploadByDownloadForm_happy_path(requestsmock, settings):
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


def test_UploadByDownloadForm_connectionerrors(requestsmock, settings):
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
