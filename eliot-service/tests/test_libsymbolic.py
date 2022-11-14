# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import types

import pytest

from eliot.libsymbolic import (
    BadDebugIDError,
    bytes_split_generator,
    convert_debug_id,
    get_module_filename,
    parse_sym_file,
    ParseSymFileError,
)


TESTPROJ_SYM = """\
MODULE Linux x86_64 D48F191186D67E69DF025AD71FB91E1F0 testproj
FILE 0 /home/willkg/projects/testproj/src/main.rs
FUNC 5380 44 0 testproj::main
5380 9 1 0
5389 36 2 0
53bf 5 3 0
"""


def test_bytes_split_generator():
    symfile = (
        "MODULE windows x86_64 0185139C8F04FFC94C4C44205044422E1 xul.pdb\n"
        "INFO CODE_ID 60533C886EFD000 xul.dll\n"
        "FILE 0 hg:hg.mozilla.org/releases/mozilla-release:media/libjpeg/simd/etc\n"
    )
    symfile_bytes = symfile.encode("utf-8")
    # This should return the same as splitlines()--the difference is that it's
    # returning a generator
    assert isinstance(bytes_split_generator(symfile_bytes, b"\n"), types.GeneratorType)
    assert (
        list(bytes_split_generator(symfile_bytes, b"\n")) == symfile_bytes.splitlines()
    )


def test_get_module_filename_no_info():
    """No INFO line should return debug_filename"""
    symfile = (
        "MODULE Linux x86_64 D48F191186D67E69DF025AD71FB91E1F0 testproj\n"
        "FILE 0 /home/willkg/projects/testproj/src/main.rs\n"
        "FUNC 5380 44 0 testproj::main\n"
    )
    symfile_bytes = symfile.encode("utf-8")
    assert get_module_filename(symfile_bytes, "testproj") == "testproj"


def test_get_module_no_pe_filename():
    symfile = (
        "MODULE Linux x86_64 6C0CFDB91476E3E45DCB01FABB49DDA90 libxul.so\n"
        "INFO CODE_ID B9FD0C6C7614E4E35DCB01FABB49DDA913586357\n"
        "FILE 0 /build/firefox-ifRHdl/firefox-87.0+build3/memory/volatile/etc\n"
    )
    symfile_bytes = symfile.encode("utf-8")
    assert get_module_filename(symfile_bytes, "libxul.so") == "libxul.so"


def test_convert_debug_id():
    assert (
        convert_debug_id("58C99D979ADA4CD795F8740CE23C2E1F2")
        == "58c99d97-9ada-4cd7-95f8-740ce23c2e1f-2"
    )


def test_convert_debug_id_bad():
    with pytest.raises(BadDebugIDError):
        convert_debug_id("bad_id")


def test_parse_sym_file_malformed(tmpdir):
    debug_filename = "testproj"
    debug_id = "D48F191186D67E69DF025AD71FB91E1F0"
    data = b"this is junk"

    with pytest.raises(ParseSymFileError) as excinfo:
        parse_sym_file(debug_filename, debug_id, data, tmpdir)

    assert excinfo.value.reason_code == "sym_malformed"


def test_parse_sym_file_lookup_error(tmpdir):
    debug_filename = "testproj"
    # This is the wrong debugid for that sym file
    debug_id = "000000000000000000000000000000000"
    data = TESTPROJ_SYM.encode("utf-8")

    with pytest.raises(ParseSymFileError) as excinfo:
        parse_sym_file(debug_filename, debug_id, data, tmpdir)

    assert excinfo.value.reason_code == "sym_debug_id_lookup_error"
