# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from unittest.mock import ANY
from urllib.parse import unquote

import pytest

from systemtests.lib.fake_data import FakeZipArchive
from systemtests.lib.tecken_client import TeckenClient


# Mark all tests in this module as upload tests
pytestmark = pytest.mark.upload

small_archive_param = pytest.param((2**19, "windows"), id="small")
large_archive_param = pytest.param(
    (2**30, "linux"), id="large", marks=pytest.mark.large_files
)

small_and_large_archives = pytest.mark.parametrize(
    "zip_archive", [small_archive_param, large_archive_param], indirect=True
)
small_archive = pytest.mark.parametrize(
    "zip_archive", [small_archive_param], indirect=True
)


class TestDirectUpload:
    # Tests within a class scope are executed in definition order.

    @small_and_large_archives
    def test_upload(self, tecken_client: TeckenClient, zip_archive: FakeZipArchive):
        response = tecken_client.upload(zip_archive.file_name)
        assert response.status_code == 201
        zip_archive.uploaded = True

    @small_and_large_archives
    def test_download(self, tecken_client: TeckenClient, zip_archive: FakeZipArchive):
        if not zip_archive.uploaded:
            pytest.skip("upload failed")

        for sym_file in zip_archive.members:
            response = tecken_client.download(sym_file.key())
            assert response.status_code == 200
            [redirect] = response.history
            assert redirect.status_code == 302

    @small_archive
    def test_head_request(
        self, tecken_client: TeckenClient, zip_archive: FakeZipArchive
    ):
        if not zip_archive.uploaded:
            pytest.skip("upload failed")

        for sym_file in zip_archive.members:
            response = tecken_client.download(sym_file.key(), method="HEAD")
            assert response.status_code == 200
            assert not response.history

    @small_archive
    @pytest.mark.nginx
    def test_headers(self, tecken_client: TeckenClient, zip_archive: FakeZipArchive):
        if not zip_archive.uploaded:
            pytest.skip("upload failed")

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

    @small_archive
    def test_code_info_lookup(
        self, tecken_client: TeckenClient, zip_archive: FakeZipArchive
    ):
        if not zip_archive.uploaded:
            pytest.skip("upload failed")

        for sym_file in zip_archive.members:
            response = tecken_client.download(
                sym_file.code_info_key(), allow_redirects=False
            )
            assert response.status_code == 302
            redirect_key = unquote(response.headers["location"])[1:]
            assert redirect_key == sym_file.key()


class TestDirectTryUpload:
    # Tests within a class scope are executed in definition order.

    @small_archive
    def test_upload(self, tecken_client: TeckenClient, zip_archive: FakeZipArchive):
        response = tecken_client.upload(zip_archive.file_name, try_storage=True)
        assert response.status_code == 201
        zip_archive.uploaded = True

    @small_archive
    def test_download(self, tecken_client: TeckenClient, zip_archive: FakeZipArchive):
        if not zip_archive.uploaded:
            pytest.skip("upload failed")

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
