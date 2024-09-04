# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from typing import Callable
import pytest

from systemtests.lib.fake_data import FakeDataBucket, FakeZipArchive
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
@pytest.mark.write_bucket
def test_upload_and_download(
    size: int,
    platform: str,
    tecken_client: TeckenClient,
    create_zip_archive: Callable[[int, str], FakeZipArchive],
    fake_data_bucket: FakeDataBucket,
):
    zip_archive = create_zip_archive(size, platform)
    url = fake_data_bucket.upload_scratch(zip_archive.file_name)
    response = tecken_client.upload_by_download(url)
    assert response.status_code == 201

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
