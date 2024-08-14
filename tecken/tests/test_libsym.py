# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pytest

from tecken.libsym import extract_sym_header_data, SymParseError


class Test_extract_sym_header_data:
    def test_windows_module_header(self, tmp_path):
        sym_path = tmp_path / "js.sym"
        sym_path.write_bytes(
            b"""\
MODULE windows x86_64 A7B74D36BC7FECE04C4C44205044422E1 js.pdb
INFO CODE_ID 66BCC3E020DC000 js.exe
INFO RELEASECHANNEL beta
INFO VERSION 130.0
INFO VENDOR Mozilla
INFO PRODUCTNAME Firefox
INFO BUILDID 20240814121850
INFO GENERATOR mozilla/dump_syms 2.3.3
FILE 0 hg:hg.mozilla.org/releases/mozilla-beta:build/pure_virtual/pure_virtual.c:2107f27bbb2a2d2adc4cd4a4ae9bed8234b88d5d
FILE 1 hg:hg.mozilla.org/releases/mozilla-beta:mfbt/Assertions.h:2107f27bbb2a2d2adc4cd4a4ae9bed8234b88d5d
"""
        )
        data = extract_sym_header_data(str(sym_path))
        assert data == {
            "debug_filename": "js.pdb",
            "debug_id": "A7B74D36BC7FECE04C4C44205044422E1",
            "code_file": "js.exe",
            "code_id": "66BCC3E020DC000",
            "generator": "mozilla/dump_syms 2.3.3",
        }

    def test_mac_module_headeer(self, tmp_path):
        sym_path = tmp_path / "libmozglue.dylib.sym"
        sym_path.write_bytes(
            b"""\
MODULE Mac x86_64 16039459CC413A18B31815B77A73C0E90 libmozglue.dylib
INFO CODE_ID 16039459CC413A18B31815B77A73C0E9
INFO RELEASECHANNEL beta
INFO VERSION 130.0
INFO VENDOR Mozilla
INFO PRODUCTNAME Firefox
INFO BUILDID 20240814121850
INFO GENERATOR mozilla/dump_syms 2.3.3
FILE 0 hg:hg.mozilla.org/releases/mozilla-beta:build/pure_virtual/pure_virtual.c:2107f27bbb2a2d2adc4cd4a4ae9bed8234b88d5d
FILE 1 hg:hg.mozilla.org/releases/mozilla-beta:memory/build/zone.c:2107f27bbb2a2d2adc4cd4a4ae9bed8234b88d5d
"""
        )
        data = extract_sym_header_data(str(sym_path))
        assert data == {
            "debug_filename": "libmozglue.dylib",
            "debug_id": "16039459CC413A18B31815B77A73C0E90",
            "code_file": "",
            "code_id": "16039459CC413A18B31815B77A73C0E9",
            "generator": "mozilla/dump_syms 2.3.3",
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
        sym_path = tmp_path / "libnss3.so.sym"
        sym_path.write_bytes(
            b"""\
MODULE Linux x86_64 A4CE852C227BB0DBB18BD1B5D75C51430 libnss3.so
INFO CODE_ID 2C85CEA47B22DBB0B18BD1B5D75C5143DE916497
INFO RELEASECHANNEL beta
INFO VERSION 130.0
INFO VENDOR Mozilla
INFO PRODUCTNAME Fennec
INFO BUILDID 20240814121850
INFO GENERATOR mozilla/dump_syms 2.3.3
FILE 0 s3:gecko-generated-sources:d6462856db6d74cac7a8c3828d23875b0b668975ee2a5b37015c86ce722a1c88164de511853077a5652b435e1ed37079b307ade8744777a21022400bb396c2a7/build/unix/elfhack/inject/x86_64-android.c:
FILE 1 /builds/worker/fetches/android-ndk/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/include/bits/fortify/string.h
"""
        )
        data = extract_sym_header_data(str(sym_path))
        assert data == {
            "debug_filename": "libnss3.so",
            "debug_id": "A4CE852C227BB0DBB18BD1B5D75C51430",
            "code_file": "",
            "code_id": "2C85CEA47B22DBB0B18BD1B5D75C5143DE916497",
            "generator": "mozilla/dump_syms 2.3.3",
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
