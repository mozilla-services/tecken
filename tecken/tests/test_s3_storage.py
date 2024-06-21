# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os

import pytest
from botocore.exceptions import ClientError

from tecken.libstorage import StorageError
from tecken.ext.s3.storage import S3Storage


INIT_CASES = {
    "https://s3.amazonaws.com/some-bucket": {
        "backend": "s3",
        "base_url": "https://s3.amazonaws.com/some-bucket",
        "endpoint_url": None,
        "name": "some-bucket",
        "prefix": "v1",
        "region": None,
    },
    "https://s3.amazonaws.com/some-bucket?access=public": {
        "backend": "s3",
        "base_url": "https://s3.amazonaws.com/some-bucket",
        "endpoint_url": None,
        "name": "some-bucket",
        "prefix": "v1",
        "region": None,
    },
    "https://s3-eu-west-2.amazonaws.com/some-bucket": {
        "backend": "s3",
        "base_url": "https://s3-eu-west-2.amazonaws.com/some-bucket",
        "endpoint_url": None,
        "name": "some-bucket",
        "prefix": "v1",
        "region": "eu-west-2",
    },
    "http://s3.example.com/buck/prfx": {
        "backend": "test-s3",
        "base_url": "http://s3.example.com/buck",
        "endpoint_url": "http://s3.example.com",
        "name": "buck",
        "prefix": "prfx/v1",
        "region": None,
    },
    "http://localstack:4566/publicbucket": {
        "backend": "emulated-s3",
        "base_url": "http://localstack:4566/publicbucket",
        "endpoint_url": "http://localstack:4566",
        "name": "publicbucket",
        "prefix": "v1",
        "region": None,
    },
}


@pytest.mark.parametrize(
    "url, expected", INIT_CASES.items(), ids=tuple(INIT_CASES.keys())
)
def test_init(url, expected):
    """The URL is processed during initialization."""
    bucket = S3Storage(url)
    assert bucket.backend == expected["backend"]
    assert bucket.base_url == expected["base_url"]
    assert bucket.endpoint_url == expected["endpoint_url"]
    assert bucket.name == expected["name"]
    assert bucket.prefix == expected["prefix"]
    assert bucket.region == expected["region"]
    assert repr(bucket)


def test_init_unknown_region_raises():
    """An exception is raised by a S3 URL with an unknown region."""
    with pytest.raises(ValueError):
        S3Storage("https://s3-unheardof.amazonaws.com/some-bucket")


def test_init_unknown_backend_raises():
    """An exception is raised if the backend can't be determined from the URL."""
    with pytest.raises(ValueError):
        S3Storage("https://unknown-backend.example.com/some-bucket")


@pytest.mark.parametrize(
    "url,file_prefix,prefix",
    (
        ("http://s3.example.com/bucket", "v0", "v0"),
        ("http://s3.example.com/bucket/try", "v0", "try/v0"),
        ("http://s3.example.com/bucket/fail/", "v1", "fail/v1"),
    ),
)
def test_init_file_prefix(url, file_prefix, prefix):
    """A file_prefix is optionally combined with the URL prefix."""
    bucket = S3Storage(url, file_prefix=file_prefix)
    assert bucket.prefix == prefix


def test_exists_s3(s3_helper):
    """exists() returns True when then S3 API returns 200."""
    bucket = S3Storage(os.environ["UPLOAD_DEFAULT_URL"])
    s3_helper.create_bucket("publicbucket")
    assert bucket.exists()


def test_exists_s3_not_found(s3_helper):
    """exists() returns False when the S3 API raises a 404 ClientError."""
    bucket = S3Storage(os.environ["UPLOAD_DEFAULT_URL"])
    assert not bucket.exists()


# FIXME(willkg): rewrite this to use s3_helper, but we need some way to make the
# bucket forbidden
# def test_exists_s3_forbidden_raises(botomock):
#     """exists() raises StorageError when the S3 API raises a 403 ClientError."""
#
#     def raise_forbidden(self, operation_name, api_params):
#         assert operation_name == "HeadBucket"
#         parsed_response = {"Error": {"Code": "403", "Message": "Forbidden"}}
#         raise ClientError(parsed_response, operation_name)
#
#     bucket = S3Storage("https://s3.amazonaws.com/some-bucket")
#     with botomock(raise_forbidden), pytest.raises(StorageError):
#         bucket.exists()


def test_exists_s3_non_client_error_raises(s3_helper):
    """exists() raises StorageError when the S3 API raises a non-client error."""

    # NOTE(willkg): nothing is listening at that port, so it kicks up a connection error
    bucket = S3Storage("http://localstack:5000/publicbucket/")
    with pytest.raises(StorageError):
        bucket.exists()


def test_storageerror_msg():
    """The StorageError message includes the URL and the backend error message."""
    bucket = S3Storage("https://s3.amazonaws.com/some-bucket?access=public")
    parsed_response = {"Error": {"Code": "403", "Message": "Forbidden"}}
    backend_error = ClientError(parsed_response, "HeadBucket")
    error = StorageError(backend=bucket.backend, url=bucket.url, error=backend_error)
    expected = (
        "s3 backend (https://s3.amazonaws.com/some-bucket?access=public)"
        " raised ClientError: An error occurred (403) when calling the HeadBucket"
        " operation: Forbidden"
    )
    assert str(error) == expected
