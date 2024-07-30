# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


import logging
import os
import tempfile
from typing import Generator

import pytest

from systemtests.lib.tecken_client import Environment, TeckenClient
from systemtests.lib.fake_data import FakeDataBucket, FakeZipArchive


LOGGER = logging.getLogger(__name__)

TMP_DIR = "./tmp"

# Custom marks are used to determine which tests to run. Tests are enabled based
# on the target environment and the command-line flags passed to pytest.
CUSTOM_MARKS = {
    "large_files": "tests with large files (slow)",
    "nginx": "tests that require nginx in fron of the app",
    "upload": "tests that upload data to the server (potentially destructive)",
    "write_bucket": "tests that require write access to the fake data GCS bucket",
}

ENVIRONMENTS = [
    Environment(
        name="local",
        base_url="http://web:8000/",
        include_marks={"upload"},
    ),
    Environment(
        name="stage",
        base_url="https://symbols.stage.mozaws.net/",
        include_marks={"upload", "nginx"},
    ),
    Environment(
        name="gcp_stage",
        base_url="https://tecken-stage.symbols.nonprod.webservices.mozgcp.net/",
        include_marks={"upload", "nginx"},
    ),
]


def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        "--target-env",
        action="store",
        choices=[env.name for env in ENVIRONMENTS],
        default="local",
        help="the target environment to run the tests against (default: local)",
    )
    parser.addoption(
        "--with-large-files",
        action="store_true",
        help="run tests that upload and download large files (slow)",
    )
    parser.addoption(
        "--with-write-bucket",
        action="store_true",
        help="run tests that require write access to the fake data bucket",
    )
    parser.addoption(
        "--bucket-public-url",
        action="store",
        default="https://tecken-system-tests.symbols.nonprod.webservices.mozgcp.net/",
        help="the public URL to access the fake data bucket",
    )
    parser.addoption(
        "--fake-data-bucket",
        action="store",
        default="moz-fx-tecken-system-tests",
        help="the name of the GCS bucket used to temporarily store uploads",
    )
    parser.addoption(
        "--gcp-credentials-file",
        action="store",
        default="gcp-credentials.json",
        help="path to the GCP credentials file for write access to the fake data bucket",
    )


INCLUDE_MARKS_KEY = pytest.StashKey[set[str]]()
TARGET_ENV_KEY = pytest.StashKey[Environment]()


def pytest_configure(config: pytest.Config):
    # Register custom marks
    for name, description in CUSTOM_MARKS.items():
        config.addinivalue_line("markers", f"{name}: {description}")

    # Store the target env in the configuration
    env_name = config.getoption("--target-env")
    for target_env in ENVIRONMENTS:
        if target_env.name == env_name:
            break
    else:
        raise pytest.UsageError("invalid target environment name")
    config.stash[TARGET_ENV_KEY] = target_env

    # Store the list of of selected marks in the configuration
    include_marks = target_env.include_marks.copy()
    if config.getoption("--with-write-bucket"):
        include_marks.add("write_bucket")
    if config.getoption("--with-large-files"):
        include_marks.add("large_files")
    config.stash[INCLUDE_MARKS_KEY] = include_marks


def pytest_sessionstart(session: pytest.Session):
    target_env = session.config.stash[TARGET_ENV_KEY]
    LOGGER.info("using Tecken base URL %s", target_env.base_url)


def pytest_runtest_setup(item: pytest.Item):
    # Skip test based on marks
    custom_marks = CUSTOM_MARKS.keys() & item.keywords
    include_marks = item.config.stash[INCLUDE_MARKS_KEY]
    if skip_marks := custom_marks - include_marks:
        skip_reason = ", ".join(f'"{mark}"' for mark in skip_marks)
        pytest.skip(f"{skip_reason} not selected for execution")


@pytest.fixture(scope="session")
def tecken_client(pytestconfig: pytest.Config) -> TeckenClient:
    target_env = pytestconfig.stash[TARGET_ENV_KEY]
    return TeckenClient(target_env)


@pytest.fixture(scope="session")
def fake_data_bucket(pytestconfig: pytest.Config) -> FakeDataBucket:
    bucket_name = pytestconfig.getoption("--fake-data-bucket")
    public_url = pytestconfig.getoption("--bucket-public-url")
    writable = pytestconfig.getoption("--with-write-bucket")
    if writable:
        credentials_path = pytestconfig.getoption("--gcp-credentials-file")
    else:
        credentials_path = None
    return FakeDataBucket(bucket_name, public_url, credentials_path)


@pytest.fixture(scope="class")
def zip_archive(
    request: pytest.FixtureRequest,
) -> Generator[FakeZipArchive, None, None]:
    size, platform = request.param
    sym_file_size = size // 2
    zip = FakeZipArchive(size, sym_file_size, platform)
    os.makedirs(TMP_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP_DIR) as tmp_dir:
        zip.create(tmp_dir)
        yield zip


@pytest.fixture(scope="class")
def zip_archive_url(
    zip_archive: FakeZipArchive, fake_data_bucket: FakeDataBucket
) -> str:
    return fake_data_bucket.upload_scratch(zip_archive.file_name)
