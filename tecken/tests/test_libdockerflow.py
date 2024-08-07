# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from unittest.mock import patch
import pytest

from tecken import libdockerflow
from tecken.base.symbolstorage import symbol_storage
from tecken.libdockerflow import get_version_info, get_release_name


def test_check_storage_urls_happy_path(symbol_storage):
    errors = libdockerflow.check_storage_urls(None)
    assert not errors


def test_check_storage_urls_missing(symbol_storage_no_create):
    errors = libdockerflow.check_storage_urls(None)
    assert len(errors) == 1
    assert symbol_storage_no_create.get_upload_backend(False).bucket in errors[0].msg
    for error in errors:
        assert "bucket not found" in error.msg
        assert error.id == "tecken.health.E001"


def test_check_storage_urls_other_error():
    storage = symbol_storage()
    exception = RuntimeError("A different error")
    with (
        patch.object(storage.upload_backend, "exists", side_effect=exception),
        pytest.raises(RuntimeError),
    ):
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
