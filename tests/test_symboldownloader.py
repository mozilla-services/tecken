# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
from io import BytesIO
from gzip import GzipFile

import pytest
# from requests.exceptions import ContentDecodingError

from tecken.base.symboldownloader import SymbolDownloader, SymbolNotFound


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


def test_has_private(s3_client):
    s3_client.create_bucket(Bucket='private')
    s3_client.put_object(
        Bucket='private',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )

    urls = (
        'https://s3.example.com/private/prefix/',
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


def test_has_private_without_prefix(s3_client):
    s3_client.create_bucket(Bucket='private')
    s3_client.put_object(
        Bucket='private',
        Key='xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )

    urls = (
        'https://s3.example.com/private',
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


def test_get_url_private(s3_client):
    s3_client.create_bucket(Bucket='private')
    s3_client.put_object(
        Bucket='private',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    url = downloader.get_symbol_url(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
    # Since we use moto to unit test all S3, we don't have much control
    # over how it puts together the presigned URL.
    # The bucket gets put in the top-domain.
    assert url.startswith('https://private.s3.amazonaws.com/')
    assert '/prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym?' in url

    url = downloader.get_symbol_url(
        'xxx.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xxx.sym'
    )
    assert url is None


def test_get_url_private_dotted_name(s3_client):
    s3_client.create_bucket(Bucket='com.example.private')
    s3_client.put_object(
        Bucket='com.example.private',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )

    urls = (
        'https://s3.example.com/com.example.private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    url = downloader.get_symbol_url(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
    # Because of the dot, the region gets put into the domain name instead.
    assert url.startswith('https://s3-{}.amazonaws.com/'.format(
        os.environ['AWS_DEFAULT_REGION']
    ))
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


def test_get_stream_private(s3_client):
    s3_client.create_bucket(Bucket='private')
    long_line = 'x' * 600
    s3_client.put_object(
        Bucket='private',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='line 1\r\nline 2\r\n{}\r\n'.format(long_line)
    )

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    stream = downloader.get_symbol_stream(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
    bucket_name, key = next(stream)
    assert bucket_name == 'private'
    assert key == 'prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
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
        list(stream)


def test_get_stream_gzipped(s3_client):
    s3_client.create_bucket(Bucket='private')
    payload = (
        b'line 1\n'
        b'line 2\n'
        b'line 3\n'
    )
    buffer_ = BytesIO()
    with GzipFile(fileobj=buffer_, mode='w') as f:
        f.write(payload)
    payload_gz = buffer_.getvalue()
    s3_client.put_object(
        Bucket='private',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body=payload_gz,
        ContentEncoding='gzip',
    )
    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    stream = downloader.get_symbol_stream(
        'xul.pdb',
        '44E4EC8C2F41492B9369D6B9A059577C2',
        'xul.sym'
    )
    bucket_name, key = next(stream)
    assert bucket_name == 'private'
    assert key == 'prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym'
    lines = list(stream)
    assert lines == [
        'line 1',
        'line 2',
        'line 3'
    ]


def test_multiple_urls_public_then_private(requestsmock, s3_client):
    s3_client.create_bucket(Bucket='public')
    s3_client.create_bucket(Bucket='private')
    s3_client.put_object(
        Bucket='private',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )
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


def test_multiple_urls_private_then_public(requestsmock, s3_client):
    s3_client.create_bucket(Bucket='public')
    s3_client.create_bucket(Bucket='private')
    s3_client.put_object(
        Bucket='private',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )
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


def test_has_private_case_insensitive_debugid(s3_client):
    s3_client.create_bucket(Bucket='private')
    s3_client.put_object(
        Bucket='private',
        Key='prefix/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
        Body='whatever'
    )

    urls = (
        'https://s3.example.com/private/prefix/',
    )
    downloader = SymbolDownloader(urls)
    assert downloader.has_symbol(
        'xul.pdb',
        '44e4ec8c2f41492b9369d6b9a059577c2',
        'xul.sym'
    )


# Commented out because there is no easy way to simulate that the
# ContentDecodingError only happens when you start *reading* the stream.
# def test_get_stream_public_content_encode_error(requestsmock):
#     def cause_content_decoding_error(request, context):
#         raise ContentDecodingError('bla!')
#
#     requestsmock.get(
#         'https://s3.example.com/public/prefix/xul.pdb/'
#         '44E4EC8C2F41492B9369D6B9A059577C2/xul.sym',
#         status_code=200,
#         text=cause_content_decoding_error
#         #exc=ContentDecodingError,
#     )
#     urls = (
#         'https://s3.example.com/public/prefix/?access=public',
#     )
#     downloader = SymbolDownloader(urls)
#     stream = downloader.get_symbol_stream(
#         'xul.pdb',
#         '44e4ec8c2f41492b9369d6b9a059577c2',
#         'xul.sym'
#     )
#     print(list(stream))
#     print('STREAM', repr(stream))
#     assert 0
