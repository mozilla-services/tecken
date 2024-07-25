# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pytest

from tecken.libsym import extract_sym_header_data, SymParseError


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
