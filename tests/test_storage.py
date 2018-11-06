# XXX rename this to something like test_storage.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import mock
import pytest
from google.cloud.storage.client import Client as google_Client

from tecken.storage import StorageBucket, scrub_credentials


def test_use_StorageBucket():
    bucket = StorageBucket("https://s3.amazonaws.com/some-bucket")
    assert bucket.name == "some-bucket"
    assert bucket.endpoint_url is None
    assert bucket.region is None
    assert bucket.private  # because it's the default
    assert bucket.base_url == "https://s3.amazonaws.com/some-bucket"

    bucket = StorageBucket("https://s3.amazonaws.com/some-bucket?access=public")
    assert bucket.name == "some-bucket"
    assert bucket.endpoint_url is None
    assert bucket.region is None
    assert not bucket.private
    assert bucket.base_url == "https://s3.amazonaws.com/some-bucket"

    bucket = StorageBucket("https://s3-eu-west-2.amazonaws.com/some-bucket")
    assert bucket.name == "some-bucket"
    assert bucket.endpoint_url is None
    assert bucket.region == "eu-west-2"
    assert bucket.base_url == "https://s3-eu-west-2.amazonaws.com/some-bucket"

    bucket = StorageBucket("http://s3.example.com/buck/prfx")
    assert bucket.name == "buck"
    assert bucket.endpoint_url == "http://s3.example.com"
    assert bucket.region is None
    assert bucket.prefix == "prfx"
    assert bucket.base_url == "http://s3.example.com/buck"

    # Just check that __repr__ it works at all
    assert repr(bucket)


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


def test_region_checking():
    bucket = StorageBucket("https://s3.amazonaws.com/some-bucket")
    assert bucket.region is None

    # a known and classic one
    bucket = StorageBucket("https://s3-us-west-2.amazonaws.com/some-bucket")
    assert bucket.region == "us-west-2"

    with pytest.raises(ValueError):
        StorageBucket("https://s3-unheardof.amazonaws.com/some-bucket")


def test_google_cloud_storage_client(gcsmock):
    bucket = StorageBucket("https://storage.googleapis.com/foo-bar-bucket")
    assert bucket.name == "foo-bar-bucket"
    client = bucket.get_storage_client()
    assert isinstance(client, google_Client)


def test_google_cloud_storage_client_with_prefix():
    bucket = StorageBucket("https://storage.googleapis.com/foo-bar-bucket/myprefix")
    assert bucket.name == "foo-bar-bucket"
    assert bucket.prefix == "myprefix"


def test_scrub_credentials():
    result = scrub_credentials("http://user:pass@storage.example.com/foo/bar?hey=ho")
    # Exactly the same minus the "user:pass"
    assert result == "http://storage.example.com/foo/bar?hey=ho"

    result = scrub_credentials("http://storage.example.com/foo/bar?hey=ho")
    # Exactly the same
    assert result == "http://storage.example.com/foo/bar?hey=ho"
