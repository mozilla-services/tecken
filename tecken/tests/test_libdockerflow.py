# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from unittest.mock import patch
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from tecken import libdockerflow
from tecken.storage import StorageBucket, StorageError
from tecken.libdockerflow import get_version_info, get_release_name


def test_check_storage_urls_happy_path():
    with patch("tecken.storage.StorageBucket.exists", return_value=True):
        assert not libdockerflow.check_storage_urls(None)


def test_check_storage_urls_missing(settings):
    settings.SYMBOL_URLS = [
        "http://s3.example.com/public",
        "http://s3.example.com/private",
    ]
    with patch("tecken.storage.StorageBucket.exists", return_value=False):
        errors = libdockerflow.check_storage_urls(None)
    assert len(errors) == 2
    assert "public" in errors[0].msg
    assert "private" in errors[1].msg
    for error in errors:
        assert "bucket not found" in error.msg
        assert error.id == "tecken.health.E001"


@pytest.mark.parametrize(
    "exception",
    (
        ClientError({"Error": {"Code": "403", "Message": "Not allowed"}}, "HeadBucket"),
        EndpointConnectionError(endpoint_url="http://s3.example.com"),
    ),
)
def test_check_storage_urls_storageerror(exception, settings):
    settings.SYMBOL_URLS = [
        "http://s3.example.com/public",
        "http://s3.example.com/private",
    ]
    fake_bucket = StorageBucket(url=settings.SYMBOL_URLS[0])
    error = StorageError(bucket=fake_bucket, backend_error=exception)
    with patch("tecken.storage.StorageBucket.exists", side_effect=error):
        errors = libdockerflow.check_storage_urls(None)
    assert len(errors) == 2
    for error in errors:
        assert str(exception) in error.msg
        assert error.id == "tecken.health.E002"


def test_check_storage_urls_other_error(settings):
    settings.SYMBOL_URLS = [
        "http://s3.example.com/public",
        "http://s3.example.com/private",
    ]
    exception = RuntimeError("A different error")
    with patch(
        "tecken.storage.StorageBucket.exists", side_effect=exception
    ), pytest.raises(RuntimeError):
        libdockerflow.check_storage_urls(None)


def test_get_version_info(tmpdir):
    fn = tmpdir.join("/version.json")
    fn.write_text(
        '{"commit": "d6ac5a5d2acf99751b91b2a3ca651d99af6b9db3"}', encoding="utf-8"
    )

    assert get_version_info(str(tmpdir)) == {
        "commit": "d6ac5a5d2acf99751b91b2a3ca651d99af6b9db3"
    }


def test_get_release_name(tmpdir):
    fn = tmpdir.join("/version.json")
    fn.write_text(
        '{"commit": "d6ac5a5d2acf99751b91b2a3ca651d99af6b9db3", "version": "44.0"}',
        encoding="utf-8",
    )
    assert get_release_name(str(tmpdir)) == "44.0:d6ac5a5d"


def test_get_release_name_no_commit(tmpdir):
    fn = tmpdir.join("/version.json")
    fn.write_text('{"version": "44.0"}', encoding="utf-8")
    assert get_release_name(str(tmpdir)) == "44.0:unknown"


def test_get_release_name_no_version(tmpdir):
    fn = tmpdir.join("/version.json")
    fn.write_text(
        '{"commit": "d6ac5a5d2acf99751b91b2a3ca651d99af6b9db3"}', encoding="utf-8"
    )
    assert get_release_name(str(tmpdir)) == "none:d6ac5a5d"


def test_get_release_name_no_file(tmpdir):
    assert get_release_name(str(tmpdir)) == "none:unknown"
