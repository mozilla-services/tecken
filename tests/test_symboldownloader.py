# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from io import BytesIO
from gzip import GzipFile

import pytest
from botocore.exceptions import ClientError
from requests.exceptions import ContentDecodingError
from requests.packages.urllib3.response import HTTPResponse

from tecken.base.symboldownloader import (
    SymbolDownloader,
    SymbolNotFound,
    iter_lines,
)


def test_iter_lines():

    class Stream:
        def __init__(self, content):
            self.left = content

        def read(self, size):
            if not self.left:
                raise StopIteration
            chunk = self.left[:size]
            self.left = self.left[size:]
            return chunk

    lines = (
        'Line 1\n'
        'Line 2\n'
        'Line 3\n'
    )
    stream = Stream(lines)
    output = list(iter_lines(stream))
    assert output == ['Line 1', 'Line 2', 'Line 3']

    # Create it again because our little stream mock doesn't rewind
    stream = Stream(lines)
    output = list(iter_lines(stream, chunk_size=5))
    assert output == ['Line 1', 'Line 2', 'Line 3']

    stream = Stream(lines.strip())  # no trailing linebreak
    output = list(iter_lines(stream))
    assert output == ['Line 1', 'Line 2', 'Line 3']

    stream = Stream(lines.strip())  # no trailing linebreak
    output = list(iter_lines(stream, chunk_size=3))
    assert output == ['Line 1', 'Line 2', 'Line 3']


def test_has_public(requestsmock):
    requestsmock.head(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=''
    )
    requestsmock.head(
        'https://s3.example.com/public/prefix/xxx.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym',
        text='Page Not Found',
        status_code=404,
    )
    urls = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    downloader = SymbolDownloader(urls)
    assert downloader.has_symbol(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
    assert not downloader.has_symbol(
        'xxx.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xxx.sym'
    )


def test_has_private_bubble_other_clienterrors(botomock):

    def mock_api_call(self, operation_name, api_params):
        parsed_response = {'Error': {'Code': '403', 'Message': 'Not found'}}
        raise ClientError(parsed_response, operation_name)

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    # Expect this to raise a ClientError because the bucket ('private')
    # doesn't exist. So boto3 would normally trigger a ClientError
    # with a code 'Forbidden'.
    with botomock(mock_api_call):
        with pytest.raises(ClientError):
            downloader.has_symbol(
                'xul.pdb',
                '44E4EC8C2F41492B9369D6B9A059577C2',
                'xul.sym'
            )


def test_has_private(botomock):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        if api_params['Prefix'].endswith('xxx.sym'):
            return {}
        # as long as it's not a ClientError, it's found
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }],
        }

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        assert downloader.time_took > 0.0
        assert not downloader.has_symbol(
            'xxx.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xxx.sym'
        )
        assert downloader.time_took > 0.0


def test_has_private_without_prefix(botomock):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        if api_params['Prefix'].endswith('xul.sym'):
            # found
            return {
                'Contents': [{
                    'Key': api_params['Prefix'],
                }],
            }
        elif api_params['Prefix'].endswith('xxx.sym'):
            # not found
            return {}

        raise NotImplementedError(api_params)

    urls = (
        'https://s3.example.com/private',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        assert not downloader.has_symbol(
            'xxx.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xxx.sym'
        )


def test_get_url_public(requestsmock):
    requestsmock.head(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=''
    )
    requestsmock.head(
        'https://s3.example.com/public/prefix/xxx.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym',
        text='Page Not Found',
        status_code=404,
    )
    urls = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    downloader = SymbolDownloader(urls)
    url = downloader.get_symbol_url(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
    assert url == (
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
    )
    url = downloader.get_symbol_url(
        'xxx.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xxx.sym'
    )
    assert url is None


def test_get_url_private(botomock):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        if api_params['Prefix'].endswith('xxx.sym'):
            # not found
            return {}
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }],
        }

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        url = downloader.get_symbol_url(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        # The bucket gets put in the top-domain.
        assert url.startswith('https://s3.example.com/')
        assert (
            '/private/prefix/xul.pdb/'
            '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym?'
        ) in url
        assert 'Expires=' in url
        assert 'AWSAccessKeyId=' in url
        assert 'Signature=' in url

        url = downloader.get_symbol_url(
            'xxx.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xxx.sym'
        )
        assert url is None

        assert len(botomock.calls) == 2


def test_get_url_private_dotted_name(botomock):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        if api_params['Prefix'].endswith('xxx.sym'):
            # not found
            return {}
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }],
        }

    urls = (
        'https://s3.example.com/com.example.private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        url = downloader.get_symbol_url(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        assert (
            '/com.example.private/prefix/xul.pdb/'
            '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym?'
        ) in url

        url = downloader.get_symbol_url(
            'xxx.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xxx.sym'
        )
        assert url is None

        assert len(botomock.calls) == 2


def test_get_stream_public(requestsmock):
    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        content=b'LINE ONE\nLINE TWO\n'
    )
    requestsmock.get(
        'https://s3.example.com/public/prefix/xxx.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym',
        content=b'Page Not Found',
        status_code=404,
    )
    urls = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    downloader = SymbolDownloader(urls)
    stream = downloader.get_symbol_stream(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
    url = next(stream)
    assert url == (
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
    )
    lines = list(stream)
    assert lines == ['LINE ONE', 'LINE TWO']
    stream = downloader.get_symbol_stream(
        'xxx.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xxx.sym'
    )
    with pytest.raises(SymbolNotFound):
        list(stream)


def test_get_stream_private(botomock):

    long_line = 'x' * 600

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'GetObject'
        if api_params['Key'].endswith('xxx.sym'):
            parsed_response = {
                'Error': {'Code': 'NoSuchKey', 'Message': 'Not found'},
            }
            raise ClientError(parsed_response, operation_name)

        return {
            'Body': BytesIO(
                bytes('line 1\r\nline 2\r\n{}\r\n'.format(long_line), 'utf-8')
            )
        }

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        stream = downloader.get_symbol_stream(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        bucket_name, key = next(stream)
        assert bucket_name == 'private'
        assert key == (
            'prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
        )
        lines = list(stream)
        assert lines == [
            'line 1',
            'line 2',
            long_line
        ]

        stream = downloader.get_symbol_stream(
            'xxx.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xxx.sym'
        )
        with pytest.raises(SymbolNotFound):
            next(stream)


def test_get_stream_gzipped(botomock):

    def mock_api_call(self, operation_name, api_params):
        payload = (
            b'line 1\n'
            b'line 2\n'
            b'line 3\n'
        )
        buffer_ = BytesIO()
        with GzipFile(fileobj=buffer_, mode='w') as f:
            f.write(payload)
        payload_gz = buffer_.getvalue()
        return {
            'ContentEncoding': 'gzip',
            'Body': BytesIO(payload_gz)
        }

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        stream = downloader.get_symbol_stream(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        bucket_name, key = next(stream)
        assert bucket_name == 'private'
        assert key == (
            'prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
        )
        lines = list(stream)
        assert lines == [
            'line 1',
            'line 2',
            'line 3'
        ]


def test_get_stream_gzipped_but_not_gzipped(botomock):

    def mock_api_call(self, operation_name, api_params):
        payload = (
            b'line 1\n'
            b'line 2\n'
            b'line 3\n'
        )
        return {
            'ContentEncoding': 'gzip',  # <-- note!
            'Body': BytesIO(payload)  # but it's not gzipped!
        }

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        stream = downloader.get_symbol_stream(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        bucket_name, key = next(stream)
        assert bucket_name == 'private'
        assert key == (
            'prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
        )
        # But when you start to stream it will realize that the file is not
        # actually gzipped and SymbolDownloader will automatically just skip
        # that file as if it doesn't exist.
        with pytest.raises(SymbolNotFound):
            next(stream)


def test_get_stream_private_other_clienterrors(botomock):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'GetObject'
        parsed_response = {
            'Error': {'Code': '403', 'Message': 'Forbidden'},
        }
        raise ClientError(parsed_response, operation_name)

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        stream = downloader.get_symbol_stream(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        with pytest.raises(ClientError):
            next(stream)


def test_multiple_urls_public_then_private(requestsmock, botomock):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        if api_params['Prefix'].endswith('xxx.sym'):
            # not found
            return {}
        # found
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }],
        }

    requestsmock.head(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=''
    )
    requestsmock.head(
        'https://s3.example.com/public/prefix/xxx.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym',
        text='Page Not Found',
        status_code=404,
    )

    urls = (
        'https://s3.example.com/public/prefix/?access=public',
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        assert not downloader.has_symbol(
            'xxx.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xxx.sym'
        )


def test_multiple_urls_private_then_public(requestsmock, botomock):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        if api_params['Prefix'].endswith('xxx.sym'):
            # not found
            return {}
        # found
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }],
        }

    requestsmock.head(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=''
    )
    requestsmock.head(
        'https://s3.example.com/public/prefix/xxx.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym',
        text='Page Not Found',
        status_code=404,
    )

    urls = (
        'https://s3.example.com/private/prefix/',
        'https://s3.example.com/public/prefix/?access=public',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            'xul.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xul.sym'
        )
        assert not downloader.has_symbol(
            'xxx.pdb',
            '44E4EC8C2F41492B9369D6B9A059577C2',
            'xxx.sym'
        )


def test_has_public_case_insensitive_debugid(requestsmock):
    requestsmock.head(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        text=''
    )
    urls = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    downloader = SymbolDownloader(urls)
    assert downloader.has_symbol(
        'xul.pdb',
        '44e4ec8c2f41492b9369d6b9a059577c2',
        'xul.sym'
    )


def test_has_private_case_insensitive_debugid(botomock):

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == 'ListObjectsV2'
        assert '44E4EC8C2F41492B9369D6B9A059577C2' in api_params['Prefix']
        # found
        return {
            'Contents': [{
                'Key': api_params['Prefix'],
            }],
        }

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            'xul.pdb',
            '44e4ec8c2f41492b9369d6b9a059577c2',
            'xul.sym'
        )


def test_get_stream_public_content_encode_error(requestsmock):

    class BreakingStreamHTTPResponse(HTTPResponse):
        def stream(self, *a, **kwargs):
            raise ContentDecodingError('something terrible!')

    requestsmock.get(
        'https://s3.example.com/public/prefix/xul.pdb/'
        '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        raw=BreakingStreamHTTPResponse(
            status=200
        )
    )
    urls = (
        'https://s3.example.com/public/prefix/?access=public',
    )
    downloader = SymbolDownloader(urls)
    stream = downloader.get_symbol_stream(
        'xul.pdb',
        '44e4ec8c2f41492b9369d6b9a059577c2',
        'xul.sym'
    )
    # Because the URL exists (hence the 200 OK), but when you start
    # streaming it, it realizes it's there's something wrong with the
    # content encoding, it captures that and consider this symbol
    # not found.
    # I.e. unable to stream its content is as bad as the file not existing.
    # And because it's not found, the whole stream lookup is exhausted and
    # it finally raises a SymbolNotFound error.
    with pytest.raises(SymbolNotFound):
        list(stream)
