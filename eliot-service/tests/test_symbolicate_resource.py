# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from io import BytesIO
from pathlib import Path
from unittest.mock import ANY

import pytest

from eliot.cache import DiskCache
from eliot.downloader import SymbolFileDownloader
from eliot.symbolicate_resource import (
    InvalidModules,
    InvalidStacks,
    ModuleInfo,
    DebugStats,
    SymbolicateBase,
    validate_modules,
    validate_stacks,
)

from tests.utils import counter


TESTPROJ_SYM = """\
MODULE Linux x86_64 D48F191186D67E69DF025AD71FB91E1F0 testproj
FILE 0 /home/willkg/projects/testproj/src/main.rs
FUNC 5380 44 0 testproj::main
5380 9 1 0
5389 36 2 0
53bf 5 3 0
"""

# $ cargo new testproj
# $ cd testproj
# $ echo $'\n[profile.release]\ndebug = true\n' >> Cargo.toml
# $ echo $'mod helper;\n\nfn main() {\n    helper::middle();\n}\n' > src/main.rs
# $ echo $'pub fn middle() {\n    inner();\n    println!("world!");\n}\n\nfn inner() {\n    print!("Hello, ");\n}\n' > src/helper.rs
# $ cargo build --release
# $ dump_syms --inlines target/release/testproj > testproj.sym
# and then remove everything that's not necessary
TESTPROJ_WITH_INLINES_SYM = """\
MODULE Linux x86_64 0905AE80CEE75A33E3CAB61C274274DE0 testproj
INFO CODE_ID 80AE0509E7CE335AE3CAB61C274274DE96049B64
FILE 0 /home/willkg/projects/testproj/src/main.rs
FILE 1 /rustc/e092d0b6b43f2de967af0887873151bb1c0b18d3/library/core/src/fmt/mod.rs
FILE 2 /home/willkg/projects/testproj/src/helper.rs
INLINE_ORIGIN 0 testproj::helper::middle
INLINE_ORIGIN 1 testproj::helper::inner
INLINE_ORIGIN 2 core::fmt::Arguments::new_v1
FUNC 7a40 85 0 testproj::main
INLINE 0 4 0 0 7a40 7d
INLINE 1 2 2 1 7a40 49
INLINE 2 7 2 2 7a40 3a
INLINE 1 3 2 2 7a89 31
7a40 7 3 0
7a47 33 392 1
7a7a f 7 2
7a89 31 392 1
7aba 3 3 2
7abd 8 5 0
7a82 5 5 2
"""


NTDLL_SYM = """\
MODULE windows x86_64 F86EB934B42FBB79B2595AA25907695C1 ntdll.pdb
INFO CODE_ID 0532197720E000 ntdll.dll
FUNC 1008 106 0 LdrpGetModuleName
PUBLIC 1120 0 LdrQueryNextListEntry
PUBLIC 1140 0 LdrQueryModuleInfoFromLdrEntry
FUNC 1260 4a 0 LdrpReadMemory
"""


@pytest.mark.parametrize(
    argnames="modules",
    argvalues=[
        # No modules specified is "valid"--there's just nothing to symbolicate against
        # so it's like a no-op
        [],
        # Empty strings are valid debug_filename/debug_id
        [
            ["", ""],
        ],
        # More valid debug_filename/debug_id combinations
        [
            ["<unknown>", "000000000000000000000000000000000"],
            ["TestTuple", "E60AA9C29CE869B87051DD17CFBE249F0"],
            ["IAccessible2proxy.dll.pdb", "F4753D4B2BE8489A897B6AF76E301E541"],
            ["qipcap.dll", "5F8599C48000"],
            ["libstdc++.so.6", "BF1B638ACD2AAFFD554335BB9E8A04DD0"],
            ["libgmodule-2.0.so.0.6600.1", "DF2A026FA3F7C2D1A9D2697E495645E20"],
            ["ASMO_449.so", "C241D045D9ACFD9928F87DF53B7AC0DE0"],
            [
                "{e824f0e4-72f7-4295-8879-d8ff4bf348d2}.xpi",
                "000000000000000000000000000000000",
            ],
            ["Font Awesome 5 Free-Solid-900.otf", "000000000000000000000000000000000"],
        ],
    ],
    ids=counter(),
)
def test_validate_modules_good(modules):
    # Good modules don't raise errors
    validate_modules(modules)


@pytest.mark.parametrize(
    argnames=("modules", "error"),
    argvalues=[
        # Test invalid modules shape
        (123, "modules must be a list"),
        (["abc"], "module index 0 does not have a debug_filename and debug_id"),
        ([["abc"]], "module index 0 does not have a debug_filename and debug_id"),
        (
            [["abc", "abc"], ["abc"]],
            "module index 1 does not have a debug_filename and debug_id",
        ),
        # Test invalid debug_filenames
        ([["(", "ABC"]], "module index 0 has an invalid debug_filename"),
        ([["[abc.so", "ABC"]], "module index 0 has an invalid debug_filename"),
        # Test invalid debug_ids
        ([["abc.so", "xyz"]], "module index 0 has an invalid debug_id"),
        ([["abc.so", "  abc"]], "module index 0 has an invalid debug_id"),
    ],
    ids=counter(),
)
def test_validate_modules_error(modules, error):
    with pytest.raises(InvalidModules, match=error):
        validate_modules(modules)


@pytest.mark.parametrize(
    argnames=("stacks", "modules"),
    argvalues=[
        # List with a stack with no frames is "valid"
        ([[]], []),
        # List with only one stack
        ([[[0, 1000]]], [["abc.so", "ABC"]]),
        ([[[0, 1000], [0, 1050]]], [["abc.so", "ABC"]]),
        # List with multiple stacks
        (
            [
                [],
                [[0, 1000], [0, 1050]],
                [[0, 2000], [0, 2010]],
            ],
            [["abc.so", "ABC"]],
        ),
        # -1 for module_index and module_offset
        ([[[-1, 1000], [0, -1]]], [["abc.so", "ABC"]]),
    ],
    ids=counter(),
)
def test_validate_stacks(stacks, modules):
    # Good modules don't raise errors
    validate_stacks(stacks, modules)


@pytest.mark.parametrize(
    argnames=("stacks", "modules", "error"),
    argvalues=[
        # List with no stacks is not valid
        ([], [], "no stacks specified"),
        # List of stacks is not a list of lists
        ("abc", [], "stacks must be a list of lists"),
        # Stack is not a list
        (["abc"], [], "stack 0 is not a list"),
        # Wrong number of elements in frame
        ([[0]], [["abc.so", "ABC"]], "stack 0 frame 0 is not a list of two items"),
        # module_index is not an int
        (
            [[["abc", 0]]],
            [["abc.so", "ABC"]],
            "stack 0 frame 0 has an invalid module_index",
        ),
        # module_index is not a valid index in modules
        (
            [[[-2, 0]]],
            [["abc.so", "ABC"]],
            "stack 0 frame 0 has a module_index that isn't in modules",
        ),
        (
            [[[100, 0]]],
            [["abc.so", "ABC"]],
            "stack 0 frame 0 has a module_index that isn't in modules",
        ),
        # module_offset is not an int
        (
            [[[0, "abc"]]],
            [["abc.so", "ABC"]],
            "stack 0 frame 0 has an invalid module_offset",
        ),
        # module_offset is < -1
        (
            [[[0, -2]]],
            [["abc.so", "ABC"]],
            "stack 0 frame 0 has an invalid module_offset",
        ),
    ],
    ids=counter(),
)
def test_validate_stacks_error(stacks, modules, error):
    with pytest.raises(InvalidStacks, match=error):
        validate_stacks(stacks, modules)


FAKE_HOST = "http://example.com/"


class TestSymbolicateBase:
    @pytest.mark.parametrize(
        "path, data, status_code, expected",
        [
            ("xul.so/ABCDE/xul.so.sym", b"", 500, None),
            ("xul.so/ABCDE/xul.so.sym", b"", 404, None),
            ("xul.so/ABCDE/xul.so.sym", b"abcde", 200, b"abcde"),
        ],
    )
    def test_download_sym_file(self, requestsmock, path, data, status_code, expected):
        """Test various HTTP responses for download_sym_file"""
        downloader = SymbolFileDownloader(source_urls=[FAKE_HOST])
        base = SymbolicateBase(downloader=downloader, cache=None, tmpdir=None)
        debug_filename, debug_id, filename = path.split("/")
        response = {"status_code": status_code}
        if data:
            response["content"] = data
        requestsmock.get(f"{FAKE_HOST}{path}", **response)
        assert base.download_sym_file(debug_filename, debug_id) == expected

    def test_download_sym_file_pdb(self, requestsmock, tmpdir):
        """Test .pdb files have extension replaced with .sym"""
        downloader = SymbolFileDownloader(source_urls=[FAKE_HOST])
        base = SymbolicateBase(downloader=downloader, cache=None, tmpdir=tmpdir)

        path = "xul.pdb/ABCDE/xul.sym"
        debug_filename, debug_id, filename = path.split("/")
        data = b"abcde"

        requestsmock.get(f"{FAKE_HOST}{path}", status_code=200, content=data)
        assert base.download_sym_file(debug_filename, debug_id) == data

    def test_parse_sym_file(self, tmpdir):
        """Verify SYM files can be parsed to a functional symcache"""
        debug_filename = "testproj"
        debug_id = "D48F191186D67E69DF025AD71FB91E1F0"
        data = TESTPROJ_SYM.encode("utf-8")

        base = SymbolicateBase(downloader=None, cache=None, tmpdir=tmpdir)
        symcache = base.parse_sym_file(debug_filename, debug_id, data)

        # To verify we got a symcache back, might as well do a lookup
        lineinfo = symcache.lookup(int("5380", 16))[0]
        assert lineinfo.symbol == "testproj::main"

    def test_parse_sym_file_malformed(self, caplog, metricsmock, tmpdir):
        """Verify parsing malformed SYM files logs an error"""
        debug_filename = "testproj"
        debug_id = "D48F191186D67E69DF025AD71FB91E1F0"
        data = b"this is junk"

        base = SymbolicateBase(downloader=None, cache=None, tmpdir=tmpdir)
        symcache = base.parse_sym_file(debug_filename, debug_id, data)
        assert symcache is None

    def test_parse_sym_file_lookup_error(self, caplog, metricsmock, tmpdir):
        """Verify bad debug_id logs and error and a metric

        This could happen if the SYM file that was uploaded was malformed in some way
        and the debug_id for the upload doesn't match a debug_id in the file.

        """
        caplog.set_level("INFO")
        debug_filename = "testproj"
        # This is the wrong debugid for that sym file
        debug_id = "000000000000000000000000000000000"
        data = TESTPROJ_SYM.encode("utf-8")

        with metricsmock as mm:
            base = SymbolicateBase(downloader=None, cache=None, tmpdir=tmpdir)
            symcache = base.parse_sym_file(debug_filename, debug_id, data)

            assert symcache is None
            assert caplog.record_tuples == [
                (
                    "eliot.libsymbolic",
                    40,
                    f"error looking up debug id in SYM file: {debug_filename} {debug_id}",
                ),
                (
                    "eliot.symbolicate_resource",
                    40,
                    f"sym file parse error: testproj '{debug_id}'",
                ),
            ]
            mm.assert_incr(
                "eliot.symbolicate.parse_sym_file.error",
                tags=["reason:sym_debug_id_lookup_error"],
            )

    def test_parse_sym_file_debugids(self, caplog, metricsmock, tmpdir):
        """Verify normalizing bad debug ids logs error and metric"""
        debug_filename = "testproj"
        # This is the wrong debugid for that sym file
        debug_id = "abcde"
        data = TESTPROJ_SYM.encode("utf-8")

        with metricsmock as mm:
            base = SymbolicateBase(downloader=None, cache=None, tmpdir=tmpdir)
            symcache = base.parse_sym_file(debug_filename, debug_id, data)

            assert symcache is None
            assert caplog.record_tuples == [
                ("eliot.symbolicate_resource", 40, "debug_id parse error: 'abcde'")
            ]
            mm.assert_incr(
                "eliot.symbolicate.parse_sym_file.error", tags=["reason:bad_debug_id"]
            )

    def test_get_symcache_in_cache(self, tmpcachedir, tmpdir):
        # Set up a DiskCache
        cache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))

        # Set up a SymbolicateBase with no downloader--we shouldn't trigger downloading
        # since the thing is in the cache already
        base = SymbolicateBase(downloader=None, cache=cache, tmpdir=tmpdir)

        # Set up the test with the data in the cache
        debug_filename = "testproj"
        debug_id = "D48F191186D67E69DF025AD71FB91E1F0"
        symcache = base.parse_sym_file(
            debug_filename, debug_id, TESTPROJ_SYM.encode("utf-8")
        )
        data = BytesIO()
        symcache.dump_into(data)
        data = {"filename": debug_filename, "symcache": data.getvalue()}

        cache_key = "%s/%s.symc" % (debug_filename, debug_id.upper())
        cache.set(cache_key, data)

        module_info = ModuleInfo(
            filename=debug_filename,
            debug_filename=debug_filename,
            debug_id=debug_id,
            has_symcache=None,
            symcache=None,
        )

        debug_stats = DebugStats()

        # Get the symcache which should be in the cache and make sure it's the
        # same one we put in
        base.get_symcache(module_info, debug_stats)
        assert module_info.symcache is not None
        assert module_info.symcache.debug_id == "d48f1911-86d6-7e69-df02-5ad71fb91e1f"

        assert debug_stats.data["cache_lookups"] == {"count": 1, "hits": 1, "time": ANY}

    def test_get_symcache_not_in_cache(self, requestsmock, tmpcachedir, tmpdir):
        # Set up a DiskCache
        cache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))

        # Set up a SymbolicateBase with a downloader
        downloader = SymbolFileDownloader(source_urls=[FAKE_HOST])
        base = SymbolicateBase(downloader=downloader, cache=cache, tmpdir=tmpdir)

        # Set up the test with the data in the cache
        debug_filename = "testproj"
        debug_id = "D48F191186D67E69DF025AD71FB91E1F0"
        data = TESTPROJ_SYM.encode("utf-8")

        requestsmock.get(
            f"{FAKE_HOST}{debug_filename}/{debug_id}/testproj.sym",
            status_code=200,
            content=data,
        )

        module_info = ModuleInfo(
            filename=debug_filename,
            debug_filename=debug_filename,
            debug_id=debug_id,
            has_symcache=None,
            symcache=None,
        )

        debug_stats = DebugStats()

        # Get the symcache which should be in the cache and make sure it's the
        # same one we put in
        base.get_symcache(module_info, debug_stats)
        assert module_info.symcache is not None
        assert module_info.symcache.debug_id == "d48f1911-86d6-7e69-df02-5ad71fb91e1f"

        assert debug_stats.data["cache_lookups"] == {"count": 1, "hits": 0, "time": ANY}

    def test_symbolicate(self, requestsmock, tmpcachedir, tmpdir):
        # Set up a DiskCache
        cache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))

        # Set up a SymbolicateBase with a downloader
        downloader = SymbolFileDownloader(source_urls=[FAKE_HOST])
        base = SymbolicateBase(downloader=downloader, cache=cache, tmpdir=tmpdir)

        # Set up the test with the data in the cache
        debug_filename = "testproj"
        debug_id = "D48F191186D67E69DF025AD71FB91E1F0"
        data = TESTPROJ_SYM.encode("utf-8")

        requestsmock.get(
            f"{FAKE_HOST}{debug_filename}/{debug_id}/testproj.sym",
            status_code=200,
            content=data,
        )

        stacks = [[[0, int("5380", 16)]]]
        modules = [["testproj", "D48F191186D67E69DF025AD71FB91E1F0"]]
        debug_stats = DebugStats()

        assert base.symbolicate(stacks, modules, debug_stats) == {
            "found_modules": {"testproj/D48F191186D67E69DF025AD71FB91E1F0": True},
            "stacks": [
                [
                    {
                        "file": "/home/willkg/projects/testproj/src/main.rs",
                        "frame": 0,
                        "function": "testproj::main",
                        "function_offset": "0x0",
                        "line": 1,
                        "module": "testproj",
                        "module_offset": "0x5380",
                    }
                ]
            ],
        }
        assert debug_stats.data == {
            "cache_lookups": {"count": 1, "hits": 0, "time": ANY},
            "downloads": {
                "count": 1,
                "size_per_module": {
                    "testproj/D48F191186D67E69DF025AD71FB91E1F0": 177,
                },
                "time_per_module": {
                    "testproj/D48F191186D67E69DF025AD71FB91E1F0": ANY,
                },
            },
        }

    def test_symbolicate_pe_file(self, requestsmock, tmpcachedir, tmpdir):
        """Test symbolication and "module" picks up the PE filename"""
        # Set up a DiskCache
        cache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))

        # Set up a SymbolicateBase with a downloader
        downloader = SymbolFileDownloader(source_urls=[FAKE_HOST])
        base = SymbolicateBase(downloader=downloader, cache=cache, tmpdir=tmpdir)

        symfile = (
            "MODULE windows x86_64 0185139C8F04FFC94C4C44205044422E1 xul.pdb\n"
            "INFO CODE_ID 60533C886EFD000 xul.dll\n"
            "FILE 0 hg:hg.mozilla.org/releases/mozilla-release:media/libjpeg/simd/etc\n"
            "FUNC 5380 44 0 somefunc\n"
            "5380 9 1 0\n"
            "5389 36 2 0\n"
            "53bf 5 3 0\n"
        )

        # Set up the test with the data in the cache
        debug_filename = "xul.pdb"
        debug_id = "0185139C8F04FFC94C4C44205044422E1"
        data = symfile.encode("utf-8")

        requestsmock.get(
            f"{FAKE_HOST}{debug_filename}/{debug_id}/xul.sym",
            status_code=200,
            content=data,
        )

        stacks = [[[0, int("5380", 16)]]]
        modules = [["xul.pdb", "0185139C8F04FFC94C4C44205044422E1"]]
        debug_stats = DebugStats()

        assert base.symbolicate(stacks, modules, debug_stats) == {
            "found_modules": {"xul.pdb/0185139C8F04FFC94C4C44205044422E1": True},
            "stacks": [
                [
                    {
                        "file": (
                            "hg:hg.mozilla.org/releases/mozilla-release"
                            ":media/libjpeg/simd/etc"
                        ),
                        "frame": 0,
                        "function": "somefunc",
                        "function_offset": "0x0",
                        "line": 1,
                        "module": "xul.dll",
                        "module_offset": "0x5380",
                    }
                ]
            ],
        }


class TestSymbolicateV4:
    PATH = "/symbolicate/v4"

    def test_cors(self, client):
        result = client.simulate_options(
            self.PATH,
            headers={
                "Origin": "example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert result.status_code == 200
        assert result.headers["Access-Control-Allow-Origin"] == "*"
        expected_headers = [
            "accept",
            "accept-encoding",
            "authorization",
            "content-type",
            "dnt",
            "origin",
            "user-agent",
            "x-csrftoken",
            "x-requested-with",
        ]
        assert result.headers["Access-Control-Expose-Headers"] == ", ".join(
            expected_headers
        )
        assert result.headers["Access-Control-Allow-Methods"] == "POST"

    def test_bad_request(self, client):
        # Wrong HTTP method
        result = client.simulate_get(self.PATH)
        assert result.status_code == 405
        assert result.headers["Content-Type"].startswith("application/json")

        # No data raises an HTTP 400
        result = client.simulate_post(self.PATH)
        assert result.status_code == 400
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.content == b'{"title": "Payload is not valid JSON"}'

        # Payload is not application/json
        result = client.simulate_post(self.PATH, params={"data": "wrongtype"})
        assert result.status_code == 400
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.content == b'{"title": "Payload is not valid JSON"}'

    def test_bad_payload_data(self, requestsmock, client):
        requestsmock.get(
            "http://symbols.example.com/xul.so/ABCDE/xul.so.sym", status_code=404
        )

        # No data at all
        result = client.simulate_post(self.PATH, json={})
        assert result.status_code == 400
        assert result.headers["Content-Type"].startswith("application/json")
        assert (
            result.content
            == b'{"title": "job has invalid stacks: no stacks specified"}'
        )

        # No stacks specified
        result = client.simulate_post(
            self.PATH, json={"modules": [["xul.so", "ABCDE"]]}
        )
        assert result.status_code == 400
        assert result.headers["Content-Type"].startswith("application/json")
        assert (
            result.content
            == b'{"title": "job has invalid stacks: no stacks specified"}'
        )

    def test_symbolication_module_missing_and_not_checked(self, requestsmock, client):
        """Test symbolication when one module returns 404 and one is not checked"""
        requestsmock.get(
            "http://symbols.example.com/testproj/D48F191186D67E69DF025AD71FB91E1F0/testproj.sym",
            status_code=404,
        )

        result = client.simulate_post(
            self.PATH,
            json={
                "stacks": [[[0, 1000], [0, 1020]]],
                "memoryMap": [
                    ["testproj", "D48F191186D67E69DF025AD71FB91E1F0"],
                    ["libc.so", "12345"],
                ],
                "version": 4,
            },
        )
        assert result.status_code == 200
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.json == {
            "knownModules": [False, None],
            "symbolicatedStacks": [["0x3e8 (in testproj)", "0x3fc (in testproj)"]],
        }

    def test_symbolication_module_200(self, requestsmock, client):
        """Test symbolication when module returns 200 and is used for symbolication"""
        requestsmock.get(
            "http://symbols.example.com/testproj/D48F191186D67E69DF025AD71FB91E1F0/testproj.sym",
            status_code=200,
            text=TESTPROJ_SYM,
        )

        result = client.simulate_post(
            self.PATH,
            json={
                "stacks": [[[0, int("5380", 16)]]],
                "memoryMap": [["testproj", "D48F191186D67E69DF025AD71FB91E1F0"]],
                "version": 4,
            },
        )
        assert result.status_code == 200
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.json == {
            # This sym file exists
            "knownModules": [True],
            "symbolicatedStacks": [["testproj::main (in testproj)"]],
        }

    def test_symbolication_module_200_with_inlines(self, requestsmock, client):
        """Test symbolication when module with inline data returns 200 and is used for symbolication"""
        requestsmock.get(
            "http://symbols.example.com/testproj/0905AE80CEE75A33E3CAB61C274274DE0/testproj.sym",
            status_code=200,
            text=TESTPROJ_WITH_INLINES_SYM,
        )

        result = client.simulate_post(
            self.PATH,
            json={
                "stacks": [[[0, int("7a40", 16)]]],
                "memoryMap": [["testproj", "0905AE80CEE75A33E3CAB61C274274DE0"]],
                "version": 4,
            },
        )
        assert result.status_code == 200
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.json == {
            # This sym file exists
            "knownModules": [True],
            "symbolicatedStacks": [["testproj::main (in testproj)"]],
        }

    def test_symbolication_not_proxied(self, requestsmock, metricsmock, client):
        """Test symbolication with no TeckenProxied header"""
        requestsmock.get(
            "http://symbols.example.com/testproj/D48F191186D67E69DF025AD71FB91E1F0/testproj.sym",
            status_code=200,
            text=TESTPROJ_SYM,
        )

        with metricsmock as mm:
            result = client.simulate_post(
                self.PATH,
                json={
                    "stacks": [[[0, int("5380", 16)]]],
                    "memoryMap": [["testproj", "D48F191186D67E69DF025AD71FB91E1F0"]],
                    "version": 4,
                },
            )
            assert result.status_code == 200
            assert result.headers["Content-Type"].startswith("application/json")

            # Assert the request was not proxied
            mm.assert_incr(
                "eliot.symbolicate.proxied",
                tags=["proxied:0"],
            )

    def test_symbolication_proxied(self, requestsmock, metricsmock, client):
        """Test symbolication when TeckenProxied header exists and is 1"""
        requestsmock.get(
            "http://symbols.example.com/testproj/D48F191186D67E69DF025AD71FB91E1F0/testproj.sym",
            status_code=200,
            text=TESTPROJ_SYM,
        )

        with metricsmock as mm:
            result = client.simulate_post(
                self.PATH,
                headers={
                    "TeckenProxied": "1",
                },
                json={
                    "stacks": [[[0, int("5380", 16)]]],
                    "memoryMap": [["testproj", "D48F191186D67E69DF025AD71FB91E1F0"]],
                    "version": 4,
                },
            )
            assert result.status_code == 200
            assert result.headers["Content-Type"].startswith("application/json")

            # Assert the request was proxied
            mm.assert_incr(
                "eliot.symbolicate.proxied",
                tags=["proxied:1"],
            )


class TestSymbolicateV5:
    PATH = "/symbolicate/v5"

    def test_cors(self, client):
        result = client.simulate_options(
            self.PATH,
            headers={
                "Origin": "example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert result.status_code == 200
        assert result.headers["Access-Control-Allow-Origin"] == "*"
        expected_headers = [
            "accept",
            "accept-encoding",
            "authorization",
            "content-type",
            "dnt",
            "origin",
            "user-agent",
            "x-csrftoken",
            "x-requested-with",
        ]
        assert result.headers["Access-Control-Expose-Headers"] == ", ".join(
            expected_headers
        )
        assert result.headers["Access-Control-Allow-Methods"] == "POST"

    def test_bad_request(self, client):
        # Wrong HTTP method
        result = client.simulate_get(self.PATH)
        assert result.status_code == 405
        assert result.headers["Content-Type"].startswith("application/json")

        # No data raises an HTTP 400
        result = client.simulate_post(self.PATH)
        assert result.status_code == 400
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.content == b'{"title": "Payload is not valid JSON"}'

        # Payload is not application/json
        result = client.simulate_post(self.PATH, params={"data": "wrongtype"})
        assert result.status_code == 400
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.content == b'{"title": "Payload is not valid JSON"}'

    def test_bad_payload_data(self, requestsmock, client):
        requestsmock.get(
            "http://symbols.example.com/xul.so/ABCDE/xul.so.sym", status_code=404
        )

        # No data at all
        result = client.simulate_post(self.PATH, json={})
        assert result.status_code == 400
        assert result.headers["Content-Type"].startswith("application/json")
        assert (
            result.content
            == b'{"title": "job 0 has invalid stacks: no stacks specified"}'
        )

        # No stacks specified
        result = client.simulate_post(
            self.PATH, json={"modules": [["xul.so", "ABCDE"]]}
        )
        assert result.status_code == 400
        assert result.headers["Content-Type"].startswith("application/json")
        assert (
            result.content
            == b'{"title": "job 0 has invalid stacks: no stacks specified"}'
        )

        # No stacks specified with multiple jobs
        result = client.simulate_post(
            self.PATH,
            json={
                "jobs": [
                    # job 0
                    {"stacks": [[[0, 1000]]], "memoryMap": [["xul.so", "ABCDE"]]},
                    # job 1 which has no stacks
                    {"modules": [["xul.so", "ABCDE"]]},
                ]
            },
        )
        assert result.status_code == 400
        assert result.headers["Content-Type"].startswith("application/json")
        assert (
            result.content
            == b'{"title": "job 1 has invalid stacks: no stacks specified"}'
        )

    def test_symbolication_module_missing_and_not_checked(self, requestsmock, client):
        """Test symbolication when one module returns 404 and one is not checked"""
        requestsmock.get(
            "http://symbols.example.com/testproj/D48F191186D67E69DF025AD71FB91E1F0/testproj.sym",
            status_code=404,
        )

        result = client.simulate_post(
            self.PATH,
            json={
                "stacks": [[[0, 1000], [0, 1020]]],
                "memoryMap": [
                    ["testproj", "D48F191186D67E69DF025AD71FB91E1F0"],
                    ["libc.so", "12345"],
                ],
            },
        )
        assert result.status_code == 200
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.json == {
            "results": [
                {
                    "found_modules": {
                        # This sym file was missing
                        "testproj/D48F191186D67E69DF025AD71FB91E1F0": False,
                        # This file isn't referenced in the stacks, so it was never checked
                        "libc.so/12345": None,
                    },
                    "stacks": [
                        [
                            {
                                "frame": 0,
                                "module": "testproj",
                                "module_offset": "0x3e8",
                            },
                            {
                                "frame": 1,
                                "module": "testproj",
                                "module_offset": "0x3fc",
                            },
                        ]
                    ],
                }
            ],
        }

    def test_symbolication_module_200(self, requestsmock, client):
        """Test symbolication when module returns 200 and is used for symbolication"""
        requestsmock.get(
            "http://symbols.example.com/testproj/D48F191186D67E69DF025AD71FB91E1F0/testproj.sym",
            status_code=200,
            text=TESTPROJ_SYM,
        )

        result = client.simulate_post(
            self.PATH,
            json={
                "jobs": [
                    # job 0
                    {
                        "stacks": [[[0, int("5380", 16)]]],
                        "memoryMap": [
                            ["testproj", "D48F191186D67E69DF025AD71FB91E1F0"]
                        ],
                    },
                ]
            },
        )
        assert result.status_code == 200
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.json == {
            "results": [
                {
                    # This sym file exists
                    "found_modules": {
                        "testproj/D48F191186D67E69DF025AD71FB91E1F0": True
                    },
                    "stacks": [
                        [
                            {
                                "file": "/home/willkg/projects/testproj/src/main.rs",
                                "frame": 0,
                                "function": "testproj::main",
                                "function_offset": "0x0",
                                "line": 1,
                                "module": "testproj",
                                "module_offset": "0x5380",
                            },
                        ]
                    ],
                }
            ],
        }

    def test_symbolication_with_inlines(self, requestsmock, client):
        """Test symbolication when module returns 200 and is used for symbolication"""
        requestsmock.get(
            "http://symbols.example.com/testproj/0905AE80CEE75A33E3CAB61C274274DE0/testproj.sym",
            status_code=200,
            text=TESTPROJ_WITH_INLINES_SYM,
        )

        result = client.simulate_post(
            self.PATH,
            json={
                "jobs": [
                    # job 0
                    {
                        "stacks": [[[0, int("7a7a", 16)]]],
                        "memoryMap": [
                            ["testproj", "0905AE80CEE75A33E3CAB61C274274DE0"]
                        ],
                    },
                ]
            },
        )
        assert result.status_code == 200
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.json == {
            "results": [
                {
                    # This sym file exists
                    "found_modules": {
                        "testproj/0905AE80CEE75A33E3CAB61C274274DE0": True
                    },
                    "stacks": [
                        [
                            {
                                "inlines": [
                                    {
                                        "function": "testproj::helper::inner",
                                        "file": "/home/willkg/projects/testproj/src/helper.rs",
                                        "line": 7,
                                    },
                                    {
                                        "function": "testproj::helper::middle",
                                        "file": "/home/willkg/projects/testproj/src/helper.rs",
                                        "line": 2,
                                    },
                                ],
                                "file": "/home/willkg/projects/testproj/src/main.rs",
                                "frame": 0,
                                "function": "testproj::main",
                                "function_offset": "0x3a",
                                "line": 4,
                                "module": "testproj",
                                "module_offset": "0x7a7a",
                            },
                        ]
                    ],
                }
            ],
        }

    def test_line_and_no_file(self, requestsmock, client):
        """Test output when symbolic returns line: 0 but no file info"""
        requestsmock.get(
            "http://symbols.example.com/ntdll.pdb/F86EB934B42FBB79B2595AA25907695C1/ntdll.sym",
            status_code=200,
            text=NTDLL_SYM,
        )

        result = client.simulate_post(
            self.PATH,
            json={
                "jobs": [
                    # job 0
                    {
                        "stacks": [[[0, int("1008", 16)]]],
                        "memoryMap": [
                            ["ntdll.pdb", "F86EB934B42FBB79B2595AA25907695C1"],
                        ],
                    },
                ]
            },
        )
        assert result.status_code == 200
        assert result.headers["Content-Type"].startswith("application/json")
        assert result.json == {
            "results": [
                {
                    # This sym file exists
                    "found_modules": {
                        "ntdll.pdb/F86EB934B42FBB79B2595AA25907695C1": True
                    },
                    "stacks": [
                        [
                            {
                                "frame": 0,
                                "function": "LdrpGetModuleName",
                                "function_offset": "0x0",
                                "module": "ntdll.dll",
                                "module_offset": "0x1008",
                            },
                        ]
                    ],
                }
            ],
        }

    def test_symbolication_not_proxied(self, requestsmock, metricsmock, client):
        """Test symbolication with no TeckenProxied header"""
        requestsmock.get(
            "http://symbols.example.com/testproj/D48F191186D67E69DF025AD71FB91E1F0/testproj.sym",
            status_code=200,
            text=TESTPROJ_SYM,
        )

        with metricsmock as mm:
            result = client.simulate_post(
                self.PATH,
                json={
                    "jobs": [
                        # job 0
                        {
                            "stacks": [[[0, int("5380", 16)]]],
                            "memoryMap": [
                                ["testproj", "D48F191186D67E69DF025AD71FB91E1F0"]
                            ],
                        },
                    ]
                },
            )
            assert result.status_code == 200
            assert result.headers["Content-Type"].startswith("application/json")

            # Assert the request was proxied
            mm.assert_incr(
                "eliot.symbolicate.proxied",
                tags=["proxied:0"],
            )

    def test_symbolication_proxied(self, requestsmock, metricsmock, client):
        """Test symbolication when TeckenProxied header exists and is 1"""
        requestsmock.get(
            "http://symbols.example.com/testproj/D48F191186D67E69DF025AD71FB91E1F0/testproj.sym",
            status_code=200,
            text=TESTPROJ_SYM,
        )

        with metricsmock as mm:
            result = client.simulate_post(
                self.PATH,
                headers={"TeckenProxied": "1"},
                json={
                    "jobs": [
                        # job 0
                        {
                            "stacks": [[[0, int("5380", 16)]]],
                            "memoryMap": [
                                ["testproj", "D48F191186D67E69DF025AD71FB91E1F0"]
                            ],
                        },
                    ]
                },
            )
            assert result.status_code == 200
            assert result.headers["Content-Type"].startswith("application/json")

            # Assert the request was proxied
            mm.assert_incr(
                "eliot.symbolicate.proxied",
                tags=["proxied:1"],
            )
