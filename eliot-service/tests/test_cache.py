# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from pathlib import Path

import pytest

from eliot.cache import DiskCache

from tests.utils import counter


@pytest.mark.parametrize(
    argnames=("key", "filepath"),
    argvalues=[
        # Test empty string
        ("", "%(tmp)s"),
        # Test typical examples
        ("foo", "%(tmp)s/foo"),
        ("foo/bar/symbols.sym", "%(tmp)s/foo_bar_symbols.sym"),
        (
            "xul.pdb/61D2D4F7C2CF4DC64C4C44205044422E1/xul.sym",
            "%(tmp)s/xul.pdb_61D2D4F7C2CF4DC64C4C44205044422E1_xul.sym",
        ),
        # Test leading / and .
        ("/foo", "%(tmp)s/foo"),
        ("./foo", "%(tmp)s/foo"),
        ("..//foo", "%(tmp)s/foo"),
        # Test bad characters
        ("/foo()*$", "%(tmp)s/foo____"),
        # Test multiple / .
        ("foo/bar/baz/baz2", "%(tmp)s/foo_bar_baz_baz2"),
    ],
    ids=counter(),
)
def test_diskcache_key_to_filepath(tmpcachedir, tmpdir, key, filepath):
    diskcache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))
    assert str(diskcache.key_to_filepath(key)) == (filepath % {"tmp": str(tmpcachedir)})


class TestDiskCache:
    def test_contains(self, tmpcachedir, tmpdir):
        diskcache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))
        key = "foo___bar.sym"
        assert key not in diskcache

        diskcache.set(key, {"symcache": b"abcde"})
        assert key in diskcache

    def test_get(self, tmpcachedir, tmpdir):
        """DiskCache.get returns a bytes object of the file on the filesystem"""
        diskcache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))

        key = "foo___bar.sym"
        data = {"symfile": b"abcde"}
        filepath = diskcache.key_to_filepath(key)
        diskcache.write_to_file(filepath, data)

        assert diskcache.get(key) == data
        assert type(diskcache.get(key)) == type(data)

    def test_get_error(self, tmpcachedir, tmpdir):
        """If the key doesn't exist, a get raises a KeyError"""
        diskcache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))
        key = "foo___bar.sym"

        with pytest.raises(KeyError, match="does not exist"):
            diskcache.get(key)

    def test_get_default(self, tmpcachedir, tmpdir):
        """DiskCache.get returns default if file isn't there"""
        diskcache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))
        key = "foo/bar.sym"
        data = b"abcde"
        assert diskcache.get(key, default=data) == data

    def test_get_default_get(self, tmpcachedir, tmpdir):
        """DiskCache.get returns file even if default is specified"""
        diskcache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))
        key = "foo/bar.sym"
        data = {"symfile": b"abcde"}
        default_data = {"symfile": b"12345"}
        filepath = diskcache.key_to_filepath(key)
        diskcache.write_to_file(filepath, data)
        assert diskcache.get(key, default=default_data) == data

    def test_set(self, tmpcachedir, tmpdir):
        """DiskCache.set creates a file"""
        diskcache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))
        key = "foo/bar.sym"
        data = {"symfile": b"abcde"}

        diskcache.set(key, data)
        filepath = diskcache.key_to_filepath(key)
        assert diskcache.read_from_file(filepath) == data

    def test_set_overwrite(self, tmpcachedir, tmpdir):
        """DiskCache.set overwrites existing files"""
        diskcache = DiskCache(cachedir=Path(tmpcachedir), tmpdir=Path(tmpdir))
        key = "foo/bar.sym"
        data = {"symfile": b"abcde"}
        data2 = {"symfile": b"12345"}

        filepath = diskcache.key_to_filepath(key)
        diskcache.write_to_file(filepath, data)

        diskcache.set(key, data2)
        assert diskcache.read_from_file(filepath) == data2
