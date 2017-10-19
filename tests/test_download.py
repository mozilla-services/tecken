# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import csv
import datetime
import gzip
import os
from urllib.parse import urlparse
from io import StringIO

import pytest
import mock
from botocore.exceptions import ClientError
from markus import INCR

from django.utils import timezone
from django.core.urlresolvers import reverse
from django.core.cache import cache

from tecken.base.symboldownloader import SymbolDownloader
from tecken.download import views
from tecken.download.models import MissingSymbol, MicrosoftDownload
from tecken.download.tasks import (
    download_microsoft_symbol,
    DumpSymsError,
)
from tecken.upload.models import FileUpload


_here = os.path.dirname(__file__)
# Remember, when you cabextract this file it will always create
# a file called 'ksproxy.pdb'. Even if you rename 'ksproxy.pd_' to
# something else.
PD__FILE = os.path.join(_here, 'ksproxy.pd_')
FAKE_BROKEN_DUMP_SYMS = os.path.join(_here, 'broken_dump_syms.sh')


def reload_downloader(urls):
    """Because the tecken.download.views module has a global instance
    of SymbolDownloader created at start-up, it's impossible to easily
    change the URL if you want to test clients with a different URL.
    This function hotfixes that instance to use a different URL(s).
    """
    if isinstance(urls, str):
        urls = tuple([urls])
    views.downloader = SymbolDownloader(urls)


def test_client_happy_path(client, botomock, metricsmock):
    reload_downloader('https://s3.example.com/private/prefix/')

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }]
        }

    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
    ))
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 302
        parsed = urlparse(response['location'])
        assert parsed.netloc == 's3.example.com'
        # the pre-signed URL will have the bucket in the path
        assert parsed.path == (
            '/private/prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
        )
        assert 'Signature=' in parsed.query
        assert 'Expires=' in parsed.query
        assert 'AWSAccessKeyId=' in parsed.query

        response = client.head(url)
        assert response.status_code == 200
        assert response.content == b''

        assert response['Access-Control-Allow-Origin'] == '*'
        assert response['Access-Control-Allow-Methods'] == 'GET'


def test_client_with_debug(client, botomock, metricsmock):
    reload_downloader('https://s3.example.com/private/prefix/')

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }]
        }

    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
    ))
    with botomock(mock_api_call):
        response = client.get(url, HTTP_DEBUG='true')
        assert response.status_code == 302
        parsed = urlparse(response['location'])
        assert float(response['debug-time']) > 0
        assert parsed.netloc == 's3.example.com'
        # the pre-signed URL will have the bucket in the path
        assert parsed.path == (
            '/private/prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
        )
        assert 'Signature=' in parsed.query
        assert 'Expires=' in parsed.query
        assert 'AWSAccessKeyId=' in parsed.query

        response = client.head(url, HTTP_DEBUG='true')
        assert response.status_code == 200
        assert response.content == b''
        assert float(response['debug-time']) > 0

        # This one won't be logged because the filename is on a blacklist
        # of symbol filenames to ignore
        ignore_url = reverse('download:download_symbol', args=(
            'cxinjime.pdb',
            '342D9B0A3AE64812A2388C055C9F6C321',
            'file.ptr',
        ))
        response = client.get(ignore_url, HTTP_DEBUG='true')
        assert response.status_code == 404
        assert float(response['debug-time']) == 0.0


def test_client_with_ignorable_file_extensions(client, botomock):
    def mock_api_call(self, operation_name, api_params):
        assert False, "This mock function shouldn't be called"

    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        # Note! This is NOT in the settings.DOWNLOAD_FILE_EXTENSIONS_WHITELIST
        # list.
        'xul.xxx',
    ))
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 404


def test_client_with_debug_with_cache(client, botomock, metricsmock):
    reload_downloader('https://s3.example.com/private/prefix/')

    mock_api_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        mock_api_calls.append(api_params)
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }]
        }

    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
    ))
    with botomock(mock_api_call):
        response = client.get(url, HTTP_DEBUG='true')
        assert response.status_code == 302
        assert float(response['debug-time']) > 0

        response = client.get(url, HTTP_DEBUG='true')
        assert response.status_code == 302
        assert float(response['debug-time']) > 0

        response = client.head(url, HTTP_DEBUG='true')
        assert response.status_code == 200
        assert float(response['debug-time']) > 0

        assert len(mock_api_calls) == 1


def test_client_with_cache_refreshed(client, botomock, metricsmock):
    reload_downloader('https://s3.example.com/private/prefix/')

    mock_api_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        mock_api_calls.append(api_params)
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }]
        }

    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
    ))
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 302
        assert len(mock_api_calls) == 1

        response = client.get(url)
        assert response.status_code == 302
        assert len(mock_api_calls) == 1  # still 1

        response = client.get(url, {'_refresh': 1})
        assert response.status_code == 302
        assert len(mock_api_calls) == 2


def test_client_404(client, botomock, clear_redis_store):
    reload_downloader('https://s3.example.com/private/prefix/')

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        return {}

    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
    ))
    with botomock(mock_api_call):
        response = client.get(url)
        assert response.status_code == 404
        assert 'Symbol Not Found' in response.content.decode('utf-8')

        response = client.head(url)
        assert response.status_code == 404


def test_client_404_logged(client, botomock, clear_redis_store):
    reload_downloader('https://s3.example.com/private/prefix/')

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        return {}

    url = reverse('download:download_symbol', args=(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
    ))
    with botomock(mock_api_call):
        assert client.get(url).status_code == 404
        assert client.get(url).status_code == 404
        # This one won't be logged because it's a HEAD
        assert client.head(url).status_code == 404

        # This one won't be logged because the filename is on a blacklist
        # of symbol filenames to ignore
        ignore_url = reverse('download:download_symbol', args=(
            'cxinjime.pdb',
            '342D9B0A3AE64812A2388C055C9F6C321',
            'file.ptr',
        ))
        response = client.get(ignore_url)
        assert response.status_code == 404
        assert response.content == b'Symbol Not Found (and ignored)'

        # This one won't be logged either
        ignore_url = reverse('download:download_symbol', args=(
            'cxinjime.pdb',
            '000000000000000000000000000000000',
            'cxinjime.sym',
        ))
        response = client.get(ignore_url)
        assert response.status_code == 404
        assert response.content == b'Symbol Not Found (and ignored)'

        # This "should" have logged the missing symbols twice.
        # Actually it shouldn't log it twice because the work on logging
        # missing symbols is guarded by a memoizer that prevents it from
        # executing more than once per arguments.
        key, = list(cache.iter_keys('missingsymbols:*'))
        # The key should contain today's date
        today = timezone.now().strftime('%Y-%m-%d')
        assert today in key
        (
            symbol, debugid, filename, code_file, code_id
        ) = key.split(':')[-1].split('|')
        assert symbol == 'xul.pdb'
        assert debugid == '44E4EC8C2F41492B9369D6B9A059577C2'
        assert filename == 'xul.sym'
        assert code_file == ''
        assert code_id == ''
        value = cache.get(key)
        assert value == 1

        # Now look it up with ?code_file= and ?code_id= etc.
        assert client.get(url, {'code_file': 'xul.dll'}).status_code == 404
        assert client.get(url, {'code_id': 'deadbeef'}).status_code == 404
        # both
        assert client.get(url, {
            'code_file': 'xul.dll',
            'code_id': 'deadbeef'
        }).status_code == 404

        keys = list(cache.iter_keys('missingsymbols:*'))
        # One with neither, one with code_file, one with code_id one with both
        assert len(keys) == 4
        key, = [x for x in keys if 'deadbeef' in x and 'xul.dll' in x]
        assert cache.get(key) == 1
        (
            symbol, debugid, filename, code_file, code_id
        ) = key.split(':')[-1].split('|')
        assert symbol == 'xul.pdb'
        assert debugid == '44E4EC8C2F41492B9369D6B9A059577C2'
        assert filename == 'xul.sym'
        assert code_file == 'xul.dll'
        assert code_id == 'deadbeef'


def test_log_symbol_get_404_metrics(metricsmock):
    views.log_symbol_get_404(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
        code_file='',
        code_id='',
    )
    records = metricsmock.get_records()
    assert len(records) == 1

    # Call it again with the exact same parameters
    views.log_symbol_get_404(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
        code_file='',
        code_id='',
    )
    records = metricsmock.get_records()
    assert len(records) == 1  # unchanged

    # change one parameter slightly
    views.log_symbol_get_404(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
        code_file='',
        code_id='deadbeef',
    )
    records = metricsmock.get_records()
    assert len(records) == 2  # changed


@pytest.mark.django_db
def test_missing_symbols_csv(client, clear_redis_store):
    # Log at least one line
    views.log_symbol_get_404(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym',
        code_file='xul.dll',
        code_id='deadbeef',
    )

    url = reverse('download:missing_symbols_csv')
    response = client.get(url)
    assert response.status_code == 200
    assert response['Content-type'] == 'text/csv'
    today = timezone.now()
    yesterday = today - datetime.timedelta(days=1)
    expect_filename = yesterday.strftime('missing-symbols-%Y-%m-%d.csv')
    assert expect_filename in response['Content-Disposition']

    lines = response.content.splitlines()
    assert lines == [b'debug_file,debug_id,code_file,code_id']

    # It's empty because it reports for yesterday, but we made the
    # only log today.
    response = client.get(url, {'today': True})
    assert response.status_code == 200

    content = response.content.decode('utf-8')
    reader = csv.reader(StringIO(content))
    lines_of_lines = list(reader)
    assert len(lines_of_lines) == 2
    last_line = lines_of_lines[-1]
    assert last_line[0] == 'xul.pdb'
    assert last_line[1] == '44E4EC8C2F41492B9369D6B9A059577C2'
    assert last_line[2] == 'xul.dll'
    assert last_line[3] == 'deadbeef'


def test_get_microsoft_symbol_client(client, botomock, settings):
    settings.ENABLE_DOWNLOAD_FROM_MICROSOFT = True
    reload_downloader('https://s3.example.com/private/prefix/')

    mock_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        mock_calls.append(api_params['Prefix'])
        return {}

    url = reverse('download:download_symbol', args=(
        'foo.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'foo.sym',
    ))

    task_arguments = []

    def fake_task(symbol, debugid, **kwargs):
        task_arguments.append((symbol, debugid, kwargs))

    _mock_function = 'tecken.download.views.download_microsoft_symbol.delay'
    with mock.patch(_mock_function, new=fake_task):
        with botomock(mock_api_call):
            response = client.get(url)
            assert response.status_code == 404
            assert response.content == b'Symbol Not Found Yet'
            assert task_arguments
            task_argument, = task_arguments
            assert task_argument[0] == 'foo.pdb'
            assert task_argument[1] == '44E4EC8C2F41492B9369D6B9A059577C2'

            # Pretend we're excessively eager
            response = client.get(url)
            assert response.status_code == 404
            assert response.content == b'Symbol Not Found Yet'

            # This basically checks that the SymbolDownloader cache is
            # not invalidated between calls.
            assert len(mock_calls) == 1
            # However, the act of triggering that
            # download_microsoft_symbol.delay() call is guarded by a
            # cache. So it shouldn't have called it more than
            # once.
            assert len(task_arguments) == 1


@pytest.mark.django_db(transaction=True)
def test_download_microsoft_symbol_task_happy_path(
    botomock,
    metricsmock,
    requestsmock,
):
    with open(PD__FILE, 'rb') as f:
        content = f.read()
        # just checking that the fixture file is sane
        assert content.startswith(b'MSCF')
        requestsmock.get(
            'https://msdl.microsoft.com/download/symbols/ksproxy.pdb'
            '/A7D6F1BB18CD4CB48/ksproxy.pd_',
            content=content
        )

    def mock_api_call(self, operation_name, api_params):
        # this comes from the UPLOAD_DEFAULT_URL in settings.Test
        assert api_params['Bucket'] == 'private'

        if (
            operation_name == 'HeadObject' and
            api_params['Key'] == (
                'v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym'
            )
        ):
            # Pretend we've never heard of this
            parsed_response = {
                'Error': {'Code': '404', 'Message': 'Not found'},
            }
            raise ClientError(parsed_response, operation_name)

        if (
            operation_name == 'PutObject' and
            api_params['Key'] == (
                'v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym'
            )
        ):

            # Because .sym is in settings.COMPRESS_EXTENSIONS
            assert api_params['ContentEncoding'] == 'gzip'
            # Because .sym is in settings.MIME_OVERRIDES
            assert api_params['ContentType'] == 'text/plain'
            content = api_params['Body'].read()
            assert isinstance(content, bytes)
            # We know what the expected size is based on having run:
            #   $ cabextract ksproxy.pd_
            #   $ dump_syms ksproxy.pdb > ksproxy.sym
            #   $ ls -l ksproxy.sym
            #   1721
            assert len(content) == 729
            original_content = gzip.decompress(content)
            assert len(original_content) == 1721

            # ...pretend to actually upload it.
            return {
                # Should there be anything here?
            }

        raise NotImplementedError((operation_name, api_params))

    symbol = 'ksproxy.pdb'
    debugid = 'A7D6F1BB18CD4CB48'
    with botomock(mock_api_call):
        download_microsoft_symbol(symbol, debugid)

    # The ultimate test is that it should have created a file_upload
    file_upload, = FileUpload.objects.all()
    assert file_upload.size == 729
    assert file_upload.bucket_name == 'private'
    assert file_upload.key == 'v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym'
    assert not file_upload.update
    assert not file_upload.upload
    assert file_upload.compressed
    assert file_upload.completed_at
    assert file_upload.microsoft_download

    # It should also have created a MicrosoftDownload record.
    download_obj, = MicrosoftDownload.objects.all()
    assert download_obj.completed_at
    assert download_obj.skipped is False
    assert download_obj.error is None

    # Check that markus caught timings of the individual file processing
    records = metricsmock.get_records()
    assert len(records) == 10
    assert records[0][1] == 'tecken.download_store_missing_symbol'
    assert records[1][1] == 'tecken.download_cabextract'
    assert records[2][1] == 'tecken.download_dump_syms'
    assert records[3][1] == 'tecken.upload_file_exists'
    assert records[4][1] == 'tecken.upload_gzip_payload'
    assert records[5][1] == 'tecken.upload_put_object'
    assert records[6][1] == 'tecken.upload_file_upload_upload'
    assert records[7][1] == 'tecken.upload_file_upload'
    assert records[8][1] == (
        'tecken.download_microsoft_download_file_upload_upload'
    )
    assert records[9][1] == 'tecken.download_upload_microsoft_symbol'


@pytest.mark.django_db
def test_download_microsoft_symbol_task_skipped(
    botomock,
    metricsmock,
    requestsmock,
):
    with open(PD__FILE, 'rb') as f:
        content = f.read()
        # just checking that the fixture file is sane
        assert content.startswith(b'MSCF')
        requestsmock.get(
            'https://msdl.microsoft.com/download/symbols/ksproxy.pdb'
            '/A7D6F1BB18CD4CB48/ksproxy.pd_',
            content=content
        )

    def mock_api_call(self, operation_name, api_params):
        # this comes from the UPLOAD_DEFAULT_URL in settings.Test
        assert api_params['Bucket'] == 'private'

        if (
            operation_name == 'HeadObject' and
            api_params['Key'] == (
                'v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym'
            )
        ):
            return {'ContentLength': 729}

        raise NotImplementedError((operation_name, api_params))

    symbol = 'ksproxy.pdb'
    debugid = 'A7D6F1BB18CD4CB48'
    with botomock(mock_api_call):
        download_microsoft_symbol(symbol, debugid)

    download_obj, = MicrosoftDownload.objects.all()
    assert not download_obj.error
    assert download_obj.skipped
    assert download_obj.completed_at

    # The ultimate test is that it should NOT have created a file upload
    assert not FileUpload.objects.all().exists()

    # Check that markus caught timings of the individual file processing
    metricsmock.has_record(
        INCR, 'tecken.microsoft_download_file_upload_skip', 1, None
    )


@pytest.mark.django_db
def test_download_microsoft_symbol_task_not_found(
    botomock,
    metricsmock,
    requestsmock,
):
    requestsmock.get(
        'https://msdl.microsoft.com/download/symbols/ksproxy.pdb'
        '/A7D6F1BB18CD4CB48/ksproxy.pd_',
        content=b'Page Not Found',
        status_code=404,
    )

    def mock_api_call(self, operation_name, api_params):
        raise NotImplementedError((operation_name, api_params))

    symbol = 'ksproxy.pdb'
    debugid = 'A7D6F1BB18CD4CB48'
    with botomock(mock_api_call):
        download_microsoft_symbol(symbol, debugid)
        assert not FileUpload.objects.all().exists()
        assert not MicrosoftDownload.objects.all().exists()


@pytest.mark.django_db
def test_download_microsoft_symbol_task_wrong_file_header(
    botomock,
    metricsmock,
    requestsmock,
):
    requestsmock.get(
        'https://msdl.microsoft.com/download/symbols/ksproxy.pdb'
        '/A7D6F1BB18CD4CB48/ksproxy.pd_',
        content=b'some other junk',
    )

    def mock_api_call(self, operation_name, api_params):
        raise NotImplementedError((operation_name, api_params))

    symbol = 'ksproxy.pdb'
    debugid = 'A7D6F1BB18CD4CB48'
    with botomock(mock_api_call):
        download_microsoft_symbol(symbol, debugid)
        assert not FileUpload.objects.all().exists()

        download_obj, = MicrosoftDownload.objects.all()
        assert "did not start with 'MSCF'" in download_obj.error


@pytest.mark.django_db
def test_download_microsoft_symbol_task_cabextract_failing(
    botomock,
    metricsmock,
    requestsmock,
):
    requestsmock.get(
        'https://msdl.microsoft.com/download/symbols/ksproxy.pdb'
        '/A7D6F1BB18CD4CB48/ksproxy.pd_',
        content=b'MSCF but not a real binary',
    )

    def mock_api_call(self, operation_name, api_params):
        raise NotImplementedError((operation_name, api_params))

    symbol = 'ksproxy.pdb'
    debugid = 'A7D6F1BB18CD4CB48'
    with botomock(mock_api_call):
        download_microsoft_symbol(symbol, debugid)
        assert not FileUpload.objects.all().exists()

        download_obj, = MicrosoftDownload.objects.all()
        assert 'cabextract failed' in download_obj.error


@pytest.mark.django_db
def test_download_microsoft_symbol_task_dump_syms_failing(
    botomock,
    settings,
    metricsmock,
    requestsmock,
):
    settings.DUMP_SYMS_PATH = FAKE_BROKEN_DUMP_SYMS

    with open(PD__FILE, 'rb') as f:
        content = f.read()
        # just checking that the fixture file is sane
        assert content.startswith(b'MSCF')
        requestsmock.get(
            'https://msdl.microsoft.com/download/symbols/ksproxy.pdb'
            '/A7D6F1BB18CD4CB48/ksproxy.pd_',
            content=content
        )

    def mock_api_call(self, operation_name, api_params):
        raise NotImplementedError((operation_name, api_params))

    symbol = 'ksproxy.pdb'
    debugid = 'A7D6F1BB18CD4CB48'
    with botomock(mock_api_call):
        with pytest.raises(DumpSymsError):
            download_microsoft_symbol(symbol, debugid)

        download_obj, = MicrosoftDownload.objects.all()
        assert 'dump_syms extraction failed' in download_obj.error
        assert 'Something horrible happened' in download_obj.error


@pytest.mark.django_db
def test_store_missing_symbol_happy_path(metricsmock):
    views.store_missing_symbol('foo.pdb', 'ABCDEF12345', 'foo.sym')
    missing_symbol = MissingSymbol.objects.get(
        symbol='foo.pdb',
        debugid='ABCDEF12345',
        filename='foo.sym',
        code_file__isnull=True,
        code_id__isnull=True,
    )
    assert missing_symbol.hash
    assert missing_symbol.count == 1
    first_modified_at = missing_symbol.modified_at

    # Repeat and it should increment
    views.store_missing_symbol('foo.pdb', 'ABCDEF12345', 'foo.sym')
    missing_symbol.refresh_from_db()
    assert missing_symbol.count == 2
    assert missing_symbol.modified_at > first_modified_at

    records = metricsmock.get_records()
    assert len(records) == 2
    assert records[0][1] == 'tecken.download_store_missing_symbol'
    assert records[1][1] == 'tecken.download_store_missing_symbol'

    # This time with a code_file and code_id
    views.store_missing_symbol(
        'foo.pdb', 'ABCDEF12345', 'foo.sym',
        code_file='libsystem_pthread.dylib',
        code_id='id'
    )
    second_missing_symbol = MissingSymbol.objects.get(
        symbol='foo.pdb',
        debugid='ABCDEF12345',
        filename='foo.sym',
        code_file='libsystem_pthread.dylib',
        code_id='id',
    )
    assert second_missing_symbol.hash != missing_symbol.hash
    assert second_missing_symbol.count == 1


@pytest.mark.django_db
def test_store_missing_symbol_skips(metricsmock):
    # If either symbol, debugid or filename are too long nothing is stored
    views.store_missing_symbol('x' * 200, 'ABCDEF12345', 'foo.sym')
    views.store_missing_symbol('foo.pdb', 'x' * 200, 'foo.sym')
    views.store_missing_symbol('foo.pdb', 'ABCDEF12345', 'x' * 200)
    assert not MissingSymbol.objects.all().exists()


@pytest.mark.django_db
def test_store_missing_symbol_client(client, botomock, settings):
    settings.ENABLE_STORE_MISSING_SYMBOLS = True
    reload_downloader('https://s3.example.com/private/prefix/')

    mock_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        mock_calls.append(api_params['Prefix'])
        return {}

    url = reverse('download:download_symbol', args=(
        'foo.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'foo.ex_',
    ))

    with botomock(mock_api_call):
        response = client.get(url, {'code_file': 'something'})
        assert response.status_code == 404
        assert response.content == b'Symbol Not Found'
        assert MissingSymbol.objects.all().count() == 1

        # Pretend we're excessively eager
        response = client.get(url, {'code_file': 'something'})
        assert response.status_code == 404
        assert response.content == b'Symbol Not Found'

        # This basically checks that the SymbolDownloader cache is
        # not invalidated between calls.
        assert len(mock_calls) == 1
        # However, the act of triggering that
        # store_missing_symbol() call is guarded by a
        # cache. So it shouldn't have called it more than
        # once.
        assert MissingSymbol.objects.filter(count=1).count() == 1
