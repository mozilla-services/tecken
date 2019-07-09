# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import mock
import pytest
from google.cloud.storage import _http, blob
from google.cloud.storage.client import Client as google_Client

from tecken.storage import StorageBucket, scrub_credentials, FakeGCSClient


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


def test_emulated_gcs_client():
    bucket = StorageBucket("https://gcs-emulator.127.0.0.1.nip.io:4443/emulated-bucket")
    assert bucket.name == "emulated-bucket"
    assert bucket.is_google_cloud_storage
    assert bucket.is_emulated_gcs

    # Google Cloud Storage constants before creating a client
    orig = {
        "api_base_url": "https://www.googleapis.com",
        "api_access_endpoint": "https://storage.googleapis.com",
        "download_url_template": (
            "https://www.googleapis.com/download/storage/v1{path}?alt=media"
        ),
        "multipart_url_template": (
            "https://www.googleapis.com"
            "/upload/storage/v1{bucket_path}/o?uploadType=multipart"
        ),
        "resumable_url_template": (
            "https://www.googleapis.com"
            "/upload/storage/v1{bucket_path}/o?uploadType=resumable"
        ),
    }
    assert _http.Connection.API_BASE_URL == orig["api_base_url"]
    assert blob._API_ACCESS_ENDPOINT == orig["api_access_endpoint"]
    assert blob._DOWNLOAD_URL_TEMPLATE == orig["download_url_template"]
    assert blob._MULTIPART_URL_TEMPLATE == orig["multipart_url_template"]
    assert blob._RESUMABLE_URL_TEMPLATE == orig["resumable_url_template"]

    # Constants after creating a client
    fake = {
        "api_base_url": "https://gcs-emulator.127.0.0.1.nip.io:4443",
        "api_access_endpoint": "https://storage.gcs-emulator.127.0.0.1.nip.io:4443",
        "download_url_template": (
            "https://gcs-emulator.127.0.0.1.nip.io:4443"
            "/download/storage/v1{path}?alt=media"
        ),
        "multipart_url_template": (
            "https://gcs-emulator.127.0.0.1.nip.io:4443"
            "/upload/storage/v1{bucket_path}/o?uploadType=multipart"
        ),
        "resumable_url_template": (
            "https://gcs-emulator.127.0.0.1.nip.io:4443"
            "/upload/storage/v1{bucket_path}/o?uploadType=resumable"
        ),
    }

    with bucket.get_storage_client() as client:
        assert isinstance(client, FakeGCSClient)
        assert _http.Connection.API_BASE_URL == fake["api_base_url"]
        assert blob._API_ACCESS_ENDPOINT == fake["api_access_endpoint"]
        assert blob._DOWNLOAD_URL_TEMPLATE == fake["download_url_template"]
        assert blob._MULTIPART_URL_TEMPLATE == fake["multipart_url_template"]
        assert blob._RESUMABLE_URL_TEMPLATE == fake["resumable_url_template"]

    # Exiting client-as-context returns the constants to the original values
    assert _http.Connection.API_BASE_URL == orig["api_base_url"]
    assert blob._API_ACCESS_ENDPOINT == orig["api_access_endpoint"]
    assert blob._DOWNLOAD_URL_TEMPLATE == orig["download_url_template"]
    assert blob._MULTIPART_URL_TEMPLATE == orig["multipart_url_template"]
    assert blob._RESUMABLE_URL_TEMPLATE == orig["resumable_url_template"]


def test_fake_gcs_client_init_fake_urls():
    """URL faking can be done outside of using the FakeGCSClient."""
    server_url = "https://gcs-emulator.127.0.0.1.nip.io:4443"
    public_host = "storage.gcs-emulator.127.0.0.1.nip.io:4443"
    orig_api_base_url = "https://www.googleapis.com"
    fake_api_base_url = "https://gcs-emulator.127.0.0.1.nip.io:4443"

    # URLs can be manually faked
    FakeGCSClient.init_fake_urls(server_url, public_host)
    assert _http.Connection.API_BASE_URL == fake_api_base_url
    # A second call with the same URLs is OK
    FakeGCSClient.init_fake_urls(server_url, public_host)
    assert _http.Connection.API_BASE_URL == fake_api_base_url
    # URLs can not be changed, since they are shared with all clients
    with pytest.raises(ValueError):
        FakeGCSClient.init_fake_urls("https://example.com", public_host)
    with pytest.raises(ValueError):
        FakeGCSClient.init_fake_urls(server_url, "storage.example.com")

    # Faked URLs are undone as many times as they were faked (twice now)
    assert not FakeGCSClient.undo_fake_urls()  # False = still fake
    assert _http.Connection.API_BASE_URL == fake_api_base_url
    assert FakeGCSClient.undo_fake_urls()  # True = back to original
    assert _http.Connection.API_BASE_URL == orig_api_base_url
    assert FakeGCSClient.undo_fake_urls()  # OK to undo too many times
    assert _http.Connection.API_BASE_URL == orig_api_base_url


def test_scrub_credentials():
    result = scrub_credentials("http://user:pass@storage.example.com/foo/bar?hey=ho")
    # Exactly the same minus the "user:pass"
    assert result == "http://storage.example.com/foo/bar?hey=ho"

    result = scrub_credentials("http://storage.example.com/foo/bar?hey=ho")
    # Exactly the same
    assert result == "http://storage.example.com/foo/bar?hey=ho"
