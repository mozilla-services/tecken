# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import csv
import datetime
from urllib.parse import urlparse
from io import StringIO

from markus import TIMING

from django.utils import timezone
from django.core.urlresolvers import reverse
from django.core.cache import cache

from tecken.base.symboldownloader import SymbolDownloader
from tecken.download import views


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
