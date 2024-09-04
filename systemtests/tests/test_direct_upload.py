# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from typing import Callable
from unittest.mock import ANY
from urllib.parse import unquote

import pytest

from systemtests.lib.fake_data import FakeZipArchive
from systemtests.lib.tecken_client import TeckenClient


# Mark all tests in this module as upload tests
pytestmark = pytest.mark.upload


# Upload sizes
SMALL = 2**16
LARGE = 2**30


@pytest.mark.parametrize(
    ["size", "platform"],
    [
        pytest.param(SMALL, "windows", id="small"),
        pytest.param(LARGE, "linux", id="large", marks=pytest.mark.large_files),
    ],
)
def test_upload_and_download(
    size: int,
    platform: str,
    tecken_client: TeckenClient,
    create_zip_archive: Callable[[int, str], FakeZipArchive],
):
    zip_archive = create_zip_archive(size, platform)
    response = tecken_client.upload(zip_archive.file_name)
    assert response.status_code == 201

    for sym_file in zip_archive.members:
        response = tecken_client.download(sym_file.key())
        assert response.status_code == 200
        [redirect] = response.history
        assert redirect.status_code == 302


def test_head_request(
    tecken_client: TeckenClient,
    create_zip_archive: Callable[[int, str], FakeZipArchive],
):
    zip_archive = create_zip_archive(SMALL, "windows")
    response = tecken_client.upload(zip_archive.file_name)
    response.raise_for_status()

    for sym_file in zip_archive.members:
        response = tecken_client.download(sym_file.key(), method="HEAD")
        assert response.status_code == 200
        assert not response.history


@pytest.mark.nginx
def test_headers(
    tecken_client: TeckenClient,
    create_zip_archive: Callable[[int, str], FakeZipArchive],
):
    zip_archive = create_zip_archive(SMALL, "windows")
    response = tecken_client.upload(zip_archive.file_name)
    response.raise_for_status()

    # These are exclusively security headers added by nginx
    expected_tecken_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": ANY,
        "Strict-Transport-Security": "max-age=31536000",
    }
    # These are headers sent by the storage backend (S3 or GCS)
    expected_storage_headers = {
        "Content-Encoding": "gzip",
        "Content-Length": ANY,
    }
    response = tecken_client.download(zip_archive.members[0].key())
    [redirect] = response.history

    actual_tecken_headers = {
        name: redirect.headers[name] for name in expected_tecken_headers
    }
    assert actual_tecken_headers == expected_tecken_headers

    actual_storage_headers = {
        name: response.headers[name] for name in expected_storage_headers
    }
    assert actual_storage_headers == expected_storage_headers


def test_code_info_lookup(
    tecken_client: TeckenClient,
    create_zip_archive: Callable[[int, str], FakeZipArchive],
):
    zip_archive = create_zip_archive(SMALL, "windows")
    response = tecken_client.upload(zip_archive.file_name)
    response.raise_for_status()

    for sym_file in zip_archive.members:
        response = tecken_client.download(
            sym_file.code_info_key(), allow_redirects=False
        )
        assert response.status_code == 302
        redirect_key = unquote(response.headers["location"])[1:]
        assert redirect_key == sym_file.key()


def test_try_upload_and_download(
    tecken_client: TeckenClient,
    create_zip_archive: Callable[[int, str], FakeZipArchive],
):
    zip_archive = create_zip_archive(SMALL, "windows")
    response = tecken_client.upload(zip_archive.file_name, try_storage=True)
    assert response.status_code == 201

    for sym_file in zip_archive.members:
        # regular download should fail
        key = sym_file.key()
        response = tecken_client.download(key)
        assert response.status_code == 404

        # download using `?try` query parameter
        response = tecken_client.download(key, try_storage=True)
        assert response.status_code == 200
        [redirect] = response.history
        assert redirect.status_code == 302

        # download by prefixing the key with try/
        response = tecken_client.download(f"try/{key}")
        assert response.status_code == 200
        [redirect] = response.history
        assert redirect.status_code == 302


def test_no_token(tecken_client: TeckenClient):
    response = tecken_client.session.request(
        "POST", f"{tecken_client.base_url}/upload/"
    )
    assert response.status_code == 403
    expected_error = "This requires an Auth-Token to authenticate the request"
    assert response.json()["error"] == expected_error


def test_invalid_token(tecken_client: TeckenClient):
    response = tecken_client.auth_request("POST", "/upload/", auth_token="invalidtoken")
    assert response.status_code == 403
    expected_error = "API Token not matched"
    assert response.json()["error"] == expected_error
