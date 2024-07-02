# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
from pathlib import Path

import pytest

from tecken.upload.utils import (
    dump_and_extract,
    extract_sym_header_data,
    get_key_content_type,
    is_sym_file,
    should_compressed_key,
    SymParseError,
)


def _join(x):
    return os.path.join(os.path.dirname(__file__), x)


ZIP_FILE = _join("sample.zip")
DUPLICATED_SAME_SIZE_ZIP_FILE = _join("duplicated-same-size.zip")


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


class Test_extract_sym_header_data:
    def test_windows_module_header(self, tmp_path):
        sym_path = tmp_path / "basic-opt64.sym"
        sym_path.write_bytes(
            b"""\
MODULE windows x86_64 2B02EEDFFB7C497B9F3A107E5193B3652 basic-opt64.pdb
INFO CODE_ID 5DDC1E9E8B000 basic-opt64.dll
INFO GENERATOR mozilla/dump_syms XYZ
FILE 0 C:\\Users\\Calixte\\dump_syms\\test_data\\basic.cpp
FILE 1 d:\\agent\\_work\\2\\s\\src\\vctools\\crt\\vcstartup\\src\\heap\\delete_scalar_size.cpp
"""
        )
        data = extract_sym_header_data(str(sym_path))
        assert data == {
            "debug_filename": "basic-opt64.pdb",
            "debug_id": "2B02EEDFFB7C497B9F3A107E5193B3652",
            "code_file": "basic-opt64.dll",
            "code_id": "5DDC1E9E8B000",
            "generator": "mozilla/dump_syms XYZ",
        }

    def test_linux_header_missing_generator(self, tmp_path):
        sym_path = tmp_path / "basic.full.sym"
        sym_path.write_bytes(
            b"""\
MODULE Linux x86_64 20AD60B0B4C68177552708AA192E77390 basic.full
INFO CODE_ID B060AD20C6B47781552708AA192E7739FAC7C84A
FILE 0 /home/calixte/dev/mozilla/dump_syms.calixteman/test_data/linux/basic.cpp
PUBLIC 1000 0 _init
"""
        )
        data = extract_sym_header_data(str(sym_path))
        assert data == {
            "debug_filename": "basic.full",
            "debug_id": "20AD60B0B4C68177552708AA192E77390",
            "code_file": "",
            "code_id": "B060AD20C6B47781552708AA192E7739FAC7C84A",
            "generator": "",
        }

    def test_linux_header(self, tmp_path):
        """Verify linux module sym file headers with no code_file"""
        sym_path = tmp_path / "basic.dbg.sym"
        sym_path.write_bytes(
            b"""\
MODULE Linux x86_64 20AD60B0B4C68177552708AA192E77390 basic.full
INFO CODE_ID B060AD20C6B47781552708AA192E7739FAC7C84A
INFO GENERATOR mozilla/dump_syms XYZ
FILE 0 /home/calixte/dev/mozilla/dump_syms.calixteman/test_data/linux/basic.cpp
PUBLIC 1000 0 _init
PUBLIC 1020 0 <.plt ELF section in basic.dbg>
"""
        )
        data = extract_sym_header_data(str(sym_path))
        assert data == {
            "debug_filename": "basic.full",
            "debug_id": "20AD60B0B4C68177552708AA192E77390",
            "code_file": "",
            "code_id": "B060AD20C6B47781552708AA192E7739FAC7C84A",
            "generator": "mozilla/dump_syms XYZ",
        }

    def test_sym_parse_error(self, tmp_path):
        """Verify linux module sym file headers with no code_file"""
        sym_path = tmp_path / "basic.dbg.sym"
        sym_path.write_bytes(
            b"""\
MODULE Linux x86_64
INFO CODE_ID B060AD20C6B47781552708AA192E7739FAC7C84A
INFO GENERATOR mozilla/dump_syms XYZ
FILE 0 /home/calixte/dev/mozilla/dump_syms.calixteman/test_data/linux/basic.cpp
PUBLIC 1000 0 _init
PUBLIC 1020 0 <.plt ELF section in basic.dbg>
"""
        )
        with pytest.raises(SymParseError):
            extract_sym_header_data(str(sym_path))


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
