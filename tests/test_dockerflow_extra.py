# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from unittest.mock import call, patch, Mock
import pytest
from google.api_core.exceptions import BadRequest as google_BadRequest
from botocore.exceptions import ClientError, EndpointConnectionError

from tecken import dockerflow_extra


def test_check_redis_store_connected_happy_path():
    assert not dockerflow_extra.check_redis_store_connected(None)


def test_check_storage_urls_happy_path(gcsmock, settings):
    mock_bucket = gcsmock.MockBucket()
    gcsmock.get_bucket = lambda name: mock_bucket

    assert not dockerflow_extra.check_storage_urls(None)


def test_check_storage_urls_happy_path_s3(botomock, settings):
    settings.SYMBOL_URLS = [
        "https://s3.example.com/public/prefix/?access=public",
        "https://s3.example.com/private/prefix/",
    ]
    settings.UPLOAD_URL_EXCEPTIONS = {
        "*@peterbe.com": "https://s3.example.com/peterbe-com"
    }

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "HeadBucket"
        # These come from settings.Test
        fixture_bucket_names = ("private", "mybucket", "peterbe-com")
        assert api_params["Bucket"] in fixture_bucket_names
        return {}

    with botomock(mock_api_call):
        assert not dockerflow_extra.check_storage_urls(None)


def test_check_storage_urls_client_error(gcsmock, settings):
    def mock_get_bucket(name):
        if name == "private":
            raise google_BadRequest("Never heard of it!")
        return gcsmock.MockBucket()

    gcsmock.get_bucket = mock_get_bucket

    errors = dockerflow_extra.check_storage_urls(None)
    assert errors
    error, = errors
    assert "private" in error.msg
    assert "Never heard of it!" in error.msg


def test_check_storage_urls_client_error_s3(botomock, settings):
    settings.SYMBOL_URLS = ["https://s3.example.com/private/prefix/"]
    settings.UPLOAD_URL_EXCEPTIONS = {
        "*@peterbe.com": "https://s3.example.com/peterbe-com"
    }

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "HeadBucket"
        if api_params["Bucket"] == "private":
            response = {"Error": {"Code": "404", "Message": "Not found"}}
            raise ClientError(response, operation_name)
        return {}

    with botomock(mock_api_call):
        errors = dockerflow_extra.check_storage_urls(None)
        assert errors
        error, = errors
        assert "private" in error.msg
        assert "ClientError" in error.msg


def test_check_storage_urls_endpointconnectionerror_s3(botomock, settings):
    settings.SYMBOL_URLS = ["https://s3.example.com/private/prefix/"]
    settings.UPLOAD_URL_EXCEPTIONS = {
        "*@peterbe.com": "https://s3.example.com/peterbe-com"
    }

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "HeadBucket"
        if api_params["Bucket"] == "private":
            raise EndpointConnectionError(endpoint_url="http://s3.example.com")
        return {}

    with botomock(mock_api_call):
        errors = dockerflow_extra.check_storage_urls(None)
        assert errors
        error, = errors
        assert "private" in error.msg
        assert "EndpointConnectionError" in error.msg


def test_check_storage_urls_other_client_error_s3(botomock, settings):
    settings.SYMBOL_URLS = ["https://s3.example.com/private/prefix/"]
    settings.UPLOAD_URL_EXCEPTIONS = {
        "*@peterbe.com": "https://s3.example.com/peterbe-com"
    }

    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "HeadBucket"
        if api_params["Bucket"] == "private":
            response = {"Error": {"Code": "500", "Message": "Other"}}
            raise ClientError(response, operation_name)
        return {}

    with botomock(mock_api_call):
        with pytest.raises(ClientError):
            dockerflow_extra.check_storage_urls(None)


def test_check_storage_urls_emulated_gcs(settings):
    settings.SYMBOL_URLS = ["https://gcs-emulator.example.com/bucket"]
    settings.UPLOAD_URL_EXCEPTIONS = {
        "*@peterbe.com": "https://gcs-emulator.example.com/peterbe-com"
    }
    mock_client = Mock(spec_set=("get_bucket",))
    with patch("tecken.storage.FakeGCSClient") as mock_class:
        mock_class.return_value = mock_client
        dockerflow_extra.check_storage_urls(None)
    assert mock_class.call_count == 2
    mock_client.get_bucket.assert_has_calls((call("bucket"), call("peterbe-com")))
