# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from unittest.mock import patch
import pytest
from google.api_core.exceptions import BadRequest
from botocore.exceptions import ClientError, EndpointConnectionError

from tecken import dockerflow_extra


def test_check_redis_store_connected_happy_path():
    assert not dockerflow_extra.check_redis_store_connected(None)


def test_check_storage_urls_happy_path():
    with patch("tecken.storage.StorageBucket.exists", return_value=True):
        assert not dockerflow_extra.check_storage_urls(None)


def test_check_storage_urls_missing():
    with patch("tecken.storage.StorageBucket.exists", return_value=False):
        errors = dockerflow_extra.check_storage_urls(None)
    assert len(errors) == 2
    assert "private" in errors[0].msg
    assert "peterbe-com" in errors[1].msg
    for error in errors:
        assert "bucket not found" in error.msg
        assert error.id == "tecken.health.E003"


@pytest.mark.parametrize(
    "exception",
    (
        BadRequest("Never heard of it!"),
        ClientError({"Error": {"Code": "403", "Message": "Not allowed"}}, "HeadBucket"),
    ),
)
def test_check_storage_urls_api_error(exception):
    with patch("tecken.storage.StorageBucket.exists", side_effect=exception):
        errors = dockerflow_extra.check_storage_urls(None)
    assert len(errors) == 2
    for error in errors:
        assert str(exception) in error.msg
        assert error.id == "tecken.health.E002"


def test_check_storage_urls_endpointconnectionerror_s3():
    exception = EndpointConnectionError(endpoint_url="http://s3.example.com")
    with patch("tecken.storage.StorageBucket.exists", side_effect=exception):
        errors = dockerflow_extra.check_storage_urls(None)
    assert len(errors) == 2
    for error in errors:
        assert "Unable to connect" in error.msg
        assert error.id == "tecken.health.E001"


def test_check_storage_urls_other_client_error_s3(botomock, settings):
    exception = RuntimeError("A different error")
    with patch(
        "tecken.storage.StorageBucket.exists", side_effect=exception
    ), pytest.raises(RuntimeError):
        dockerflow_extra.check_storage_urls(None)
