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
from markus import TIMING, INCR

from django.utils import timezone
from django.core.urlresolvers import reverse
from django.core.cache import cache

from tecken.base.symboldownloader import SymbolDownloader
from tecken.download import views
from tecken.download.tasks import download_microsoft_symbol, DumpSymsError
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

        metrics_records = metricsmock.get_records()
        timing_metrics = [
            (thing, stat, value, tags)
            for thing, stat, value, tags in metrics_records
            if thing == TIMING
        ]
        assert len(timing_metrics) == 2
        assert timing_metrics[0][1] == 'tecken.download_symbol'
        assert timing_metrics[1][1] == 'tecken.download_symbol'
        assert isinstance(timing_metrics[0][2], float)
        assert isinstance(timing_metrics[1][2], float)


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


def test_client_404(client, botomock, clear_redis):
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


def test_client_404_logged(client, botomock, clear_redis):
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

        # This should have logged the missing symbols twice.
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
        assert value == 2

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


def test_missing_symbols_csv(client, clear_redis):
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
    # print(next(reader))
    # print(next(reader))
    lines_of_lines = list(reader)
    assert len(lines_of_lines) == 2
    last_line = lines_of_lines[-1]
    assert last_line[0] == 'xul.pdb'
    assert last_line[1] == '44E4EC8C2F41492B9369D6B9A059577C2'
    assert last_line[2] == 'xul.dll'
    assert last_line[3] == 'deadbeef'


def test_get_microsoft_symbol_client(client, botomock):
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

    def fake_task(symbol, debugid):
        task_arguments.append((symbol, debugid))

    _mock_function = 'tecken.download.views.download_microsoft_symbol.delay'
    with mock.patch(_mock_function, new=fake_task):
        with botomock(mock_api_call):
            response = client.get(url)
            assert response.status_code == 404
            assert response.content == b'Symbol Not Found Yet'
            assert task_arguments
            task_argument, = task_arguments
            assert task_argument == (
                'foo.pdb',
                '44E4EC8C2F41492B9369D6B9A059577C2'
            )

            # Pretend we're excessively eager
            response = client.get(url)
            assert response.status_code == 404
            assert response.content == b'Symbol Not Found Yet'

            # Whenever a download_microsoft_symbol.delay() is is MAYBE
            # called, the symboldownloader cache is invalidated on this
            # key. So the second call to symboldownloader will actually
            # reach out to S3 again.
            assert len(mock_calls) == 2
            # However, the act of triggering that
            # download_microsoft_symbol.delay() call is guarded by an
            # in-memory cache. So it shouldn't have called it more than
            # once.
            assert len(task_arguments) == 1


@pytest.mark.django_db
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
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym'
            )
        ):
            # Pretend we've never heard of this
            return {}

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
            # assert len(content) < 1721
            assert len(content) == 717
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
    assert file_upload.size == 717
    assert file_upload.bucket_name == 'private'
    assert file_upload.key == 'v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym'
    assert not file_upload.update
    assert not file_upload.upload
    assert file_upload.compressed
    assert file_upload.completed_at
    assert file_upload.microsoft_download

    # Check that markus caught timings of the individual file processing
    records = metricsmock.get_records()
    assert len(records) == 4
    assert records[0][0] == TIMING
    assert records[1][0] == TIMING
    assert records[2][0] == INCR
    assert records[3][0] == TIMING


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
            operation_name == 'ListObjectsV2' and
            api_params['Prefix'] == (
                'v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym'
            )
        ):
            return {'Contents': [
                {
                    'Key': (
                        'v0/ksproxy.pdb/A7D6F1BB18CD4CB48/ksproxy.sym'
                    ),
                    'Size': 717,
                }
            ]}

        raise NotImplementedError((operation_name, api_params))

    symbol = 'ksproxy.pdb'
    debugid = 'A7D6F1BB18CD4CB48'
    with botomock(mock_api_call):
        download_microsoft_symbol(symbol, debugid)

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
