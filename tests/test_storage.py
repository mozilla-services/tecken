# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from tecken.storage import StorageBucket, StorageError


INIT_CASES = {
    "https://s3.amazonaws.com/some-bucket": {
        "backend": "s3",
        "base_url": "https://s3.amazonaws.com/some-bucket",
        "endpoint_url": None,
        "name": "some-bucket",
        "prefix": "",
        "private": True,
        "region": None,
    },
    "https://s3.amazonaws.com/some-bucket?access=public": {
        "backend": "s3",
        "base_url": "https://s3.amazonaws.com/some-bucket",
        "endpoint_url": None,
        "name": "some-bucket",
        "prefix": "",
        "private": False,
        "region": None,
    },
    "https://s3-eu-west-2.amazonaws.com/some-bucket": {
        "backend": "s3",
        "base_url": "https://s3-eu-west-2.amazonaws.com/some-bucket",
        "endpoint_url": None,
        "name": "some-bucket",
        "prefix": "",
        "private": True,
        "region": "eu-west-2",
    },
    "http://s3.example.com/buck/prfx": {
        "backend": "test-s3",
        "base_url": "http://s3.example.com/buck",
        "endpoint_url": "http://s3.example.com",
        "name": "buck",
        "prefix": "prfx",
        "private": True,
        "region": None,
    },
    "http://minio:9000/testbucket": {
        "backend": "emulated-s3",
        "base_url": "http://minio:9000/testbucket",
        "endpoint_url": "http://minio:9000",
        "name": "testbucket",
        "prefix": "",
        "private": True,
        "region": None,
    },
}


@pytest.mark.parametrize(
    "url, expected", INIT_CASES.items(), ids=tuple(INIT_CASES.keys())
)
def test_init(url, expected):
    """The URL is processed during initialization."""
    bucket = StorageBucket(url)
    assert bucket.backend == expected["backend"]
    assert bucket.base_url == expected["base_url"]
    assert bucket.endpoint_url == expected["endpoint_url"]
    assert bucket.name == expected["name"]
    assert bucket.prefix == expected["prefix"]
    assert bucket.private == expected["private"]
    assert bucket.region == expected["region"]
    assert repr(bucket)


def test_init_unknown_region_raises():
    """An exception is raised by a S3 URL with an unknown region."""
    with pytest.raises(ValueError):
        StorageBucket("https://s3-unheardof.amazonaws.com/some-bucket")


def test_init_unknown_backend_raises():
    """An exception is raised if the backend can't be determined from the URL."""
    with pytest.raises(ValueError):
        StorageBucket("https://unknown-backend.example.com/some-bucket")


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
    bucket = StorageBucket(url, file_prefix=file_prefix)
    assert bucket.prefix == prefix


def test_exists_s3(botomock):
    """exists() returns True when then S3 API returns 200."""

    def return_200(self, operation_name, api_params):
        assert operation_name == "HeadBucket"
        return {"ReponseMetadata": {"HTTPStatusCode": 200}}

    bucket = StorageBucket("https://s3.amazonaws.com/some-bucket")
    with botomock(return_200):
        assert bucket.exists()


def test_exists_s3_not_found(botomock):
    """exists() returns False when the S3 API raises a 404 ClientError."""

    def raise_not_found(self, operation_name, api_params):
        assert operation_name == "HeadBucket"
        parsed_response = {
            "Error": {"Code": "404", "Message": "The specified bucket does not exist"}
        }
        raise ClientError(parsed_response, operation_name)

    bucket = StorageBucket("https://s3.amazonaws.com/some-bucket")
    with botomock(raise_not_found):
        assert not bucket.exists()


def test_exists_s3_forbidden_raises(botomock):
    """exists() raises StorageError when the S3 API raises a 403 ClientError."""

    def raise_forbidden(self, operation_name, api_params):
        assert operation_name == "HeadBucket"
        parsed_response = {"Error": {"Code": "403", "Message": "Forbidden"}}
        raise ClientError(parsed_response, operation_name)

    bucket = StorageBucket("https://s3.amazonaws.com/some-bucket")
    with botomock(raise_forbidden), pytest.raises(StorageError):
        bucket.exists()


def test_exists_s3_non_client_error_raises(botomock):
    """exists() raises StorageError when the S3 API raises a non-client error."""

    def raise_conn_error(self, operation_name, api_params):
        assert operation_name == "HeadBucket"
        raise EndpointConnectionError(endpoint_url="https://s3.amazonaws.com/")

    bucket = StorageBucket("https://s3.amazonaws.com/some-bucket")
    with botomock(raise_conn_error), pytest.raises(StorageError):
        bucket.exists()


def test_storageerror_msg():
    """The StorageError message includes the URL and the backend error message."""
    bucket = StorageBucket("https://s3.amazonaws.com/some-bucket?access=public")
    parsed_response = {"Error": {"Code": "403", "Message": "Forbidden"}}
    backend_error = ClientError(parsed_response, "HeadBucket")
    error = StorageError(bucket, backend_error)
    expected = (
        "s3 backend (https://s3.amazonaws.com/some-bucket?access=public)"
        " raised ClientError: An error occurred (403) when calling the HeadBucket"
        " operation: Forbidden"
    )
    assert str(error) == expected


def test_StorageBucket_client():

    mock_session = mock.Mock()

    client_kwargs_calls = []
    client_args_calls = []

    def get_client(*args, **kwargs):
        client_args_calls.append(args)
        client_kwargs_calls.append(kwargs)
        return mock.Mock()

    mock_session.client.side_effect = get_client

    def new_session():
        return mock_session

    with mock.patch("tecken.storage.boto3.session.Session", new=new_session):
        bucket = StorageBucket("https://s3.amazonaws.com/some-bucket")
        client = bucket.client
        client_again = bucket.client
        assert client_again is client
        # Only 1 session should have been created
        assert len(mock_session.mock_calls) == 1
        assert "endpoint_url" not in client_kwargs_calls[-1]

        # make a client that requires an endpoint_url
        bucket = StorageBucket("http://s3.example.com/buck/prefix")
        bucket.client
        assert client_kwargs_calls[-1]["endpoint_url"] == ("http://s3.example.com")

        # make a client that requires a different region
        bucket = StorageBucket("https://s3-eu-west-2.amazonaws.com/some-bucket")
        bucket.client
        assert client_kwargs_calls[-1]["region_name"] == ("eu-west-2")
