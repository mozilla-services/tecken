# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pytest

from systemtests.lib.fake_data import FakeZipArchive
from systemtests.lib.tecken_client import TeckenClient


# Mark all tests in this module as upload tests
pytestmark = pytest.mark.upload

small_archive_param = pytest.param((2**19, "windows"), id="small")
large_archive_param = pytest.param(
    (3 * 2**30, "linux"), id="large", marks=pytest.mark.large_files
)

small_and_large_archives = pytest.mark.parametrize(
    "zip_archive", [small_archive_param, large_archive_param], indirect=True
)
small_archive = pytest.mark.parametrize(
    "zip_archive", [small_archive_param], indirect=True
)


@pytest.mark.write_bucket
class TestUploadByDownload:
    # Tests within a class scope are executed in definition order.

    @small_and_large_archives
    def test_upload(
        self,
        tecken_client: TeckenClient,
        zip_archive: FakeZipArchive,
        zip_archive_url: str,
    ):
        response = tecken_client.upload_by_download(zip_archive_url)
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


def test_disallowed_domain(tecken_client: TeckenClient):
    response = tecken_client.upload_by_download("https://www.mozilla.org/")
    assert response.status_code == 400
    expected_error = "Not an allowed domain ('www.mozilla.org') to download from."
    assert response.json()["error"] == expected_error
