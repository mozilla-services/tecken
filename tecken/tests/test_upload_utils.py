# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
from pathlib import Path

import pytest

from tecken.upload.utils import (
    dump_and_extract,
    get_key_content_type,
    is_sym_file,
    should_compressed_key,
)


def get_path(x):
    return os.path.join(os.path.dirname(__file__), x)


ZIP_FILE = get_path("data/sample.zip")
DUPLICATED_SAME_SIZE_ZIP_FILE = get_path("data/duplicated-same-size.zip")


def test_dump_and_extract(tmpdir):
    with open(ZIP_FILE, "rb") as fp:
        file_listings = dump_and_extract(str(tmpdir), fp, ZIP_FILE)

    # That .zip file has multiple files in it so it's hard to rely on the order.
    assert len(file_listings) == 3
    for file_listing in file_listings:
        assert file_listing.path
        assert os.path.isfile(file_listing.path)
        assert file_listing.name
        assert not file_listing.name.startswith("/")
        assert file_listing.size
        assert file_listing.size == os.stat(file_listing.path).st_size

    # Inside the tmpdir there should now exist these files. Know thy fixtures...
    assert Path(tmpdir / "xpcshell.dbg").is_dir()
    assert Path(tmpdir / "flag").is_dir()
    assert Path(tmpdir / "build-symbols.txt").is_file()


def test_dump_and_extract_duplicate_name_same_size(tmpdir):
    with open(DUPLICATED_SAME_SIZE_ZIP_FILE, "rb") as f:
        file_listings = dump_and_extract(str(tmpdir), f, DUPLICATED_SAME_SIZE_ZIP_FILE)
    # Even though the file contains 2 files.
    assert len(file_listings) == 1


@pytest.mark.parametrize(
    "key, expected",
    [
        ("", False),
        ("foo", False),
        ("foo.sym", True),
        ("FOO.SYM", True),
        ("foo.exe", False),
    ],
)
def test_is_sym_file(key, expected):
    assert is_sym_file(key) == expected


@pytest.mark.parametrize(
    "key, expected",
    [
        ("", False),
        ("foo.bar", True),
        ("foo.BAR", True),
        ("foo.exe", False),
    ],
)
def test_should_compressed_key(settings, key, expected):
    settings.COMPRESS_EXTENSIONS = ["bar"]
    assert should_compressed_key(key) == expected


@pytest.mark.parametrize(
    "key, expected",
    [
        ("", None),
        ("foo.bar", None),
        ("foo.html", "text/html"),
        ("foo.HTML", "text/html"),
    ],
)
def test_get_key_content_type(settings, key, expected):
    settings.MIME_OVERRIDES = {"html": "text/html"}
    assert get_key_content_type(key) == expected
