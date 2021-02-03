# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from io import BytesIO
from gzip import GzipFile

import pytest
from botocore.exceptions import ClientError
from requests.exceptions import ContentDecodingError
from requests.packages.urllib3.response import HTTPResponse

from tecken.storage import StorageBucket
from tecken.base.symboldownloader import (
    SymbolDownloader,
    SymbolNotFound,
    iter_lines,
    exists_in_source,
)


def test_exists_in_source(botomock, settings):

    mock_api_calls = []

    def mock_api_call(self, operation_name, api_params):
        mock_api_calls.append(api_params)
        assert operation_name == "ListObjectsV2"
        if api_params["Prefix"].endswith("xxx.sym"):
            return {}
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    bucket = StorageBucket("https://s3.example.com/private")
    with botomock(mock_api_call):
        assert not exists_in_source(bucket, "xxx.sym")
        assert exists_in_source(bucket, "xul.sym")
        assert len(mock_api_calls) == 2

        # again
        assert not exists_in_source(bucket, "xxx.sym")
        assert exists_in_source(bucket, "xul.sym")
        assert len(mock_api_calls) == 2


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

    lines = "Line 1\n" "Line 2\n" "Line 3\n"
    stream = Stream(lines)
    output = list(iter_lines(stream))
    assert output == ["Line 1", "Line 2", "Line 3"]

    # Create it again because our little stream mock doesn't rewind
    stream = Stream(lines)
    output = list(iter_lines(stream, chunk_size=5))
    assert output == ["Line 1", "Line 2", "Line 3"]

    stream = Stream(lines.strip())  # no trailing linebreak
    output = list(iter_lines(stream))
    assert output == ["Line 1", "Line 2", "Line 3"]

    stream = Stream(lines.strip())  # no trailing linebreak
    output = list(iter_lines(stream, chunk_size=3))
    assert output == ["Line 1", "Line 2", "Line 3"]


def test_has_public(requestsmock):
    requestsmock.head(
        "https://s3.example.com/public/prefix/v0/xul.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        text="",
    )
    requestsmock.head(
        "https://s3.example.com/public/prefix/v0/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )
    urls = ("https://s3.example.com/public/prefix/?access=public",)
    downloader = SymbolDownloader(urls, file_prefix="v0")
    assert downloader.has_symbol(
        "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
    )
    assert not downloader.has_symbol(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )


def test_has_private_bubble_other_clienterrors(botomock):
    def mock_api_call(self, operation_name, api_params):
        parsed_response = {"Error": {"Code": "403", "Message": "Not found"}}
        raise ClientError(parsed_response, operation_name)

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    # Expect this to raise a ClientError because the bucket ('private')
    # doesn't exist. So boto3 would normally trigger a ClientError
    # with a code 'Forbidden'.
    with botomock(mock_api_call):
        with pytest.raises(ClientError):
            downloader.has_symbol(
                "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
            )


def test_has_private(botomock):
    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        if api_params["Prefix"].endswith("xxx.sym"):
            return {}
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert downloader.time_took > 0.0
        assert not downloader.has_symbol(
            "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
        )
        assert downloader.time_took > 0.0


def test_has_private_caching_and_invalidation(botomock):

    mock_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        mock_calls.append(api_params["Prefix"])
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert len(mock_calls) == 1
        assert downloader.has_symbol(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        # This should be cached
        assert len(mock_calls) == 1

        # Now invalidate it
        downloader.invalidate_cache(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert downloader.has_symbol(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert len(mock_calls) == 2

        # Invalidating unrecognized keys shouldn't break anything
        downloader.invalidate_cache(
            "never", "44E4EC8C2F41492B9369D6B9A059577C2", "heardof"
        )


def test_get_url_private_caching_and_invalidation(botomock):

    mock_calls = []

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        mock_calls.append(api_params["Prefix"])
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.get_symbol_url(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert len(mock_calls) == 1
        assert downloader.get_symbol_url(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        # This should be cached
        assert len(mock_calls) == 1

        # Now invalidate it
        downloader.invalidate_cache(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert downloader.get_symbol_url(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert len(mock_calls) == 2


def test_has_private_without_prefix(botomock):
    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        if api_params["Prefix"].endswith("xul.sym"):
            # found
            return {"Contents": [{"Key": api_params["Prefix"]}]}
        elif api_params["Prefix"].endswith("xxx.sym"):
            # not found
            return {}

        raise NotImplementedError(api_params)

    urls = ("https://s3.example.com/private",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert not downloader.has_symbol(
            "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
        )


def test_get_url_public(requestsmock):
    requestsmock.head(
        "https://s3.example.com/public/prefix/v0/xul.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        text="",
    )
    requestsmock.head(
        "https://s3.example.com/public/prefix/v0/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )
    urls = ("https://s3.example.com/public/prefix/?access=public",)
    downloader = SymbolDownloader(urls)
    url = downloader.get_symbol_url(
        "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
    )
    assert url == (
        "https://s3.example.com/public/prefix/v0/xul.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
    )
    url = downloader.get_symbol_url(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )
    assert url is None


def test_get_url_private(botomock):
    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        if api_params["Prefix"].endswith("xxx.sym"):
            # not found
            return {}
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        url = downloader.get_symbol_url(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        # The bucket gets put in the top-domain.
        assert url.startswith("https://s3.example.com/")
        assert (
            "/private/prefix/v0/xul.pdb/" "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym?"
        ) in url
        assert "Expires=" in url
        assert "AWSAccessKeyId=" in url
        assert "Signature=" in url

        url = downloader.get_symbol_url(
            "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
        )
        assert url is None

        assert len(botomock.calls) == 2


def test_public_default_file_prefix(requestsmock, settings):
    """The idea with settings.SYMBOL_FILE_PREFIX is to make it easier
    to specify the settings.SYMBOL_URLS. That settings.SYMBOL_FILE_PREFIX
    is *always* used when uploading symbols. So it's *always* useful to
    query for symbols with a prefix. However, it's an easy mistake to make
    that you just focus on the bucket name to say where symbols come from.
    In those cases, the code should "protect" you can make sure we actually
    use the prefix.

    However, we don't want to lose the flexibility to actually override
    it on a *per URL* basis.
    """
    # settings.SYMBOL_FILE_PREFIX = 'myprfx'

    requestsmock.head(
        "https://s3.example.com/public/start/myprfx/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )
    requestsmock.head(
        "https://s3.example.com/also-public/prrffxx/myprfx/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )
    requestsmock.head(
        "https://s3.example.com/special/myprfx/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )

    urls = (
        "https://s3.example.com/public/start/?access=public",
        # No trailing / in the path part
        "https://s3.example.com/also-public/prrffxx?access=public",
        # No prefix!
        "https://s3.example.com/special?access=public",
    )
    downloader = SymbolDownloader(urls, file_prefix="myprfx")
    assert not downloader.has_symbol(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )

    requestsmock.get(
        "https://s3.example.com/public/start/myprfx/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )
    requestsmock.get(
        "https://s3.example.com/also-public/prrffxx/myprfx/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )
    requestsmock.get(
        "https://s3.example.com/special/myprfx/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )

    stream = downloader.get_symbol_stream(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )
    # Now try to stream it
    with pytest.raises(SymbolNotFound):
        list(stream)


def test_private_default_file_prefix(botomock, settings):
    """See doc string in test_public_default_file_prefix"""
    all_mock_calls = []

    def mock_api_call(self, operation_name, api_params):
        if operation_name == "ListObjectsV2":
            # the has_symbol() was called
            all_mock_calls.append(api_params["Prefix"])
            # pretend it doesn't exist
            return {}
        elif operation_name == "GetObject":
            # someone wants a stream
            all_mock_calls.append(api_params["Key"])
            parsed_response = {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)
        else:
            raise NotImplementedError(operation_name)

    urls = (
        # Private URL with prefix and trailing /
        "https://s3.example.com/priv-bucket/borje/",
        # No trailing /
        "https://s3.example.com/also-priv-bucket/prrffxx",
        # No prefix
        "https://s3.example.com/some-bucket",
    )
    downloader = SymbolDownloader(urls, file_prefix="myprfx")
    with botomock(mock_api_call):
        assert not downloader.has_symbol(
            "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
        )

        assert len(all_mock_calls) == 3
        assert all_mock_calls[0].startswith("borje/myprfx/xxx.pdb")
        assert all_mock_calls[1].startswith("prrffxx/myprfx/xxx.pdb")
        assert all_mock_calls[2].startswith("myprfx/xxx.pdb")

        # reset the mutable recorder
        all_mock_calls = []

        stream = downloader.get_symbol_stream(
            "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
        )
        with pytest.raises(SymbolNotFound):
            next(stream)

        assert len(all_mock_calls) == 3
        assert all_mock_calls[0].startswith("borje/myprfx/xxx.pdb")
        assert all_mock_calls[1].startswith("prrffxx/myprfx/xxx.pdb")
        assert all_mock_calls[2].startswith("myprfx/xxx.pdb")


def test_get_url_private_dotted_name(botomock):
    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        if api_params["Prefix"].endswith("xxx.sym"):
            # not found
            return {}
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    urls = ("https://s3.example.com/com.example.private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        url = downloader.get_symbol_url(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert (
            "/com.example.private/prefix/v0/xul.pdb/"
            "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym?"
        ) in url

        url = downloader.get_symbol_url(
            "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
        )
        assert url is None

        assert len(botomock.calls) == 2


def test_get_stream_public(requestsmock):
    requestsmock.get(
        "https://s3.example.com/public/prefix/v0/xul.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        content=b"LINE ONE\nLINE TWO\n",
    )
    requestsmock.get(
        "https://s3.example.com/public/prefix/v0/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        content=b"Page Not Found",
        status_code=404,
    )
    urls = ("https://s3.example.com/public/prefix/?access=public",)
    downloader = SymbolDownloader(urls)
    stream = downloader.get_symbol_stream(
        "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
    )
    url = next(stream)
    assert url == (
        "https://s3.example.com/public/prefix/v0/xul.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym"
    )
    lines = list(stream)
    assert lines == ["LINE ONE", "LINE TWO"]
    stream = downloader.get_symbol_stream(
        "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
    )
    with pytest.raises(SymbolNotFound):
        list(stream)


def test_get_stream_private(botomock):

    long_line = "x" * 600

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "GetObject"
        if api_params["Key"].endswith("xxx.sym"):
            parsed_response = {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}
            raise ClientError(parsed_response, operation_name)

        return {"Body": BytesIO(bytes(f"line 1\r\nline 2\r\n{long_line}\r\n", "utf-8"))}

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        stream = downloader.get_symbol_stream(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        bucket_name, key = next(stream)
        assert bucket_name == "private"
        assert key == ("prefix/v0/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym")
        lines = list(stream)
        assert lines == ["line 1", "line 2", long_line]

        stream = downloader.get_symbol_stream(
            "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
        )
        with pytest.raises(SymbolNotFound):
            next(stream)


def test_get_stream_gzipped(botomock):
    def mock_api_call(self, operation_name, api_params):
        payload = b"line 1\n" b"line 2\n" b"line 3\n"
        buffer_ = BytesIO()
        with GzipFile(fileobj=buffer_, mode="w") as f:
            f.write(payload)
        payload_gz = buffer_.getvalue()
        return {"ContentEncoding": "gzip", "Body": BytesIO(payload_gz)}

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        stream = downloader.get_symbol_stream(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        bucket_name, key = next(stream)
        assert bucket_name == "private"
        assert key == ("prefix/v0/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym")
        lines = list(stream)
        assert lines == ["line 1", "line 2", "line 3"]


def test_get_stream_gzipped_but_not_gzipped(botomock):
    def mock_api_call(self, operation_name, api_params):
        payload = b"line 1\n" b"line 2\n" b"line 3\n"
        return {
            "ContentEncoding": "gzip",  # <-- note!
            "Body": BytesIO(payload),  # but it's not gzipped!
        }

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        stream = downloader.get_symbol_stream(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        bucket_name, key = next(stream)
        assert bucket_name == "private"
        assert key == ("prefix/v0/xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2/xul.sym")
        # But when you start to stream it will realize that the file is not
        # actually gzipped and SymbolDownloader will automatically just skip
        # that file as if it doesn't exist.
        with pytest.raises(SymbolNotFound):
            next(stream)


def test_get_stream_private_other_clienterrors(botomock):
    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "GetObject"
        parsed_response = {"Error": {"Code": "403", "Message": "Forbidden"}}
        raise ClientError(parsed_response, operation_name)

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        stream = downloader.get_symbol_stream(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        with pytest.raises(ClientError):
            next(stream)


def test_multiple_urls_public_then_private(requestsmock, botomock):
    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        if api_params["Prefix"].endswith("xxx.sym"):
            # not found
            return {}
        # found
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    requestsmock.head(
        "https://s3.example.com/public/prefix/v0/xul.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        text="",
    )
    requestsmock.head(
        "https://s3.example.com/public/prefix/v0/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )

    urls = (
        "https://s3.example.com/public/prefix/?access=public",
        "https://s3.example.com/private/prefix/",
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert not downloader.has_symbol(
            "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
        )


def test_multiple_urls_private_then_public(requestsmock, botomock):
    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        if api_params["Prefix"].endswith("xxx.sym"):
            # not found
            return {}
        # found
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    requestsmock.head(
        "https://s3.example.com/public/prefix/v0/xul.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        text="",
    )
    requestsmock.head(
        "https://s3.example.com/public/prefix/v0/xxx.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xxx.sym",
        text="Page Not Found",
        status_code=404,
    )

    urls = (
        "https://s3.example.com/private/prefix/",
        "https://s3.example.com/public/prefix/?access=public",
    )
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            "xul.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xul.sym"
        )
        assert not downloader.has_symbol(
            "xxx.pdb", "44E4EC8C2F41492B9369D6B9A059577C2", "xxx.sym"
        )


def test_has_public_case_insensitive_debugid(requestsmock):
    requestsmock.head(
        "https://s3.example.com/public/prefix/v0/xul.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        text="",
    )
    urls = ("https://s3.example.com/public/prefix/?access=public",)
    downloader = SymbolDownloader(urls)
    assert downloader.has_symbol(
        "xul.pdb", "44e4ec8c2f41492b9369d6b9a059577c2", "xul.sym"
    )


def test_has_private_case_insensitive_debugid(botomock):
    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "ListObjectsV2"
        assert "44E4EC8C2F41492B9369D6B9A059577C2" in api_params["Prefix"]
        # found
        return {"Contents": [{"Key": api_params["Prefix"]}]}

    urls = ("https://s3.example.com/private/prefix/",)
    downloader = SymbolDownloader(urls)
    with botomock(mock_api_call):
        assert downloader.has_symbol(
            "xul.pdb", "44e4ec8c2f41492b9369d6b9a059577c2", "xul.sym"
        )


def test_get_stream_public_content_encode_error(requestsmock):
    class BreakingStreamHTTPResponse(HTTPResponse):
        def stream(self, *a, **kwargs):
            raise ContentDecodingError("something terrible!")

    requestsmock.get(
        "https://s3.example.com/public/prefix/v0/xul.pdb/"
        "44E4EC8C2F41492B9369D6B9A059577C2/xul.sym",
        raw=BreakingStreamHTTPResponse(status=200),
    )
    urls = ("https://s3.example.com/public/prefix/?access=public",)
    downloader = SymbolDownloader(urls)
    stream = downloader.get_symbol_stream(
        "xul.pdb", "44e4ec8c2f41492b9369d6b9a059577c2", "xul.sym"
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
