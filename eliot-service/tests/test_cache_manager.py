# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pathlib

from everett.manager import ConfigManager, ConfigDictEnv, ConfigOSEnv
import pytest

from eliot.cache_manager import get_cache_manager


class DiskCacheManagerTestClient:
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
        self.cache_manager.setup()

    @classmethod
    def build_config(cls, new_config=None):
        """Build ConfigManager using environment and overrides."""
        new_config = new_config or {}
        config_manager = ConfigManager(
            environments=[ConfigDictEnv(new_config), ConfigOSEnv()]
        )
        return config_manager.with_namespace("eliot")

    def rebuild(self, new_config=None):
        """Rebuilds the client

        This is helpful if you've changed configuration and need to rebuild the
        client so that components pick up the new configuration.

        :arg new_config: dict of configuration to override normal values to build the
            new app with

        """
        self.cache_manager = get_cache_manager(self.build_config(new_config))
        self.cache_manager.setup()


@pytest.fixture
def cm_client(tmpdir):
    """Test cache manager setup with tmpdir."""
    config = {
        "ELIOT_SYMBOLS_CACHE_DIR": str(tmpdir),
    }
    config_manager = DiskCacheManagerTestClient.build_config(config)
    dcmtc = DiskCacheManagerTestClient(get_cache_manager(config_manager))
    try:
        yield dcmtc
    finally:
        dcmtc.cache_manager.shutdown()
        del dcmtc.cache_manager


def test_no_existing_files(cm_client, tmpdir):
    # Rebuild with the tmpdir we're using
    cm_client.rebuild({"ELIOT_SYMBOLS_CACHE_DIR": str(tmpdir)})

    cm = cm_client.cache_manager
    cm.run_once()

    assert len(cm.lru) == 0
    assert cm.total_size == 0


def test_existing_files(cm_client, tmpdir):
    pathlib.Path(tmpdir / "cache" / "xul__ABCDE.symc").write_bytes(b"abcde")
    pathlib.Path(tmpdir / "cache" / "xul__01234.symc").write_bytes(b"abcdef")

    # Rebuild with the tmpdir we're using
    cm_client.rebuild({"ELIOT_SYMBOLS_CACHE_DIR": str(tmpdir)})

    cm = cm_client.cache_manager
    cm.run_once()

    assert len(cm.lru) == 2
    assert cm.total_size == 11


def test_addfiles(cm_client, tmpdir):
    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(tmpdir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager
    cm.run_once()

    # We've got a fresh cache manager with nothing in it
    assert cm.lru == {}
    assert cm.total_size == 0

    # Add one 5-byte file and run loop and make sure it's in the LRU
    file1 = pathlib.Path(tmpdir / "cache" / "xul__5byte.symc")
    file1.write_bytes(b"abcde")
    cm.run_once()
    assert cm.lru == {str(file1): 5}
    assert cm.total_size == 5

    # Add one 4-byte file and run loop and now we've got two files in the LRU
    file2 = pathlib.Path(tmpdir / "cache" / "xul__4byte.symc")
    file2.write_bytes(b"abcd")
    cm.run_once()
    assert cm.lru == {str(file1): 5, str(file2): 4}
    assert cm.total_size == 9


def test_eviction_when_too_big(cm_client, tmpdir):
    cachedir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(cachedir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager
    cm.run_once()

    # We've got a fresh cache manager with nothing in it
    assert cm.lru == {}
    assert cm.total_size == 0

    # Add one 5-byte file and run loop and make sure it's in the LRU
    file1 = cachedir / "cache" / "xul__5byte.symc"
    file1.write_bytes(b"abcde")

    # Add one 4-byte file and run loop and now we've got two files in the LRU
    file2 = cachedir / "cache" / "xul__4byte.symc"
    file2.write_bytes(b"abcd")
    cm.run_once()
    assert cm.lru == {str(file1): 5, str(file2): 4}
    assert cm.total_size == 9

    # Add 1-byte file which gets total size to 10
    file3 = cachedir / "cache" / "xul__3byte.symc"
    file3.write_bytes(b"a")
    cm.run_once()
    assert cm.lru == {str(file1): 5, str(file2): 4, str(file3): 1}
    assert cm.total_size == 10

    # Add file4 of 6 bytes should evict file1 and file2
    file4 = cachedir / "cache" / "xul__6byte.symc"
    file4.write_bytes(b"abcdef")
    cm.run_once()
    assert cm.lru == {str(file3): 1, str(file4): 6}
    assert cm.total_size == 7

    # Verify what's in the cache dir on disk
    files = [str(path) for path in (cachedir / "cache").iterdir()]
    assert sorted(files) == sorted([str(file3), str(file4)])


def test_eviction_of_least_recently_used(cm_client, tmpdir):
    cachedir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(cachedir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager
    cm.run_once()

    # We've got a fresh cache manager with nothing in it
    assert cm.lru == {}
    assert cm.total_size == 0

    # Add some files
    file1 = cachedir / "cache" / "xul__rose.symc"
    file1.write_bytes(b"ab")

    file2 = cachedir / "cache" / "xul__dandelion.symc"
    file2.write_bytes(b"ab")

    file3 = cachedir / "cache" / "xul__orchid.symc"
    file3.write_bytes(b"ab")

    file4 = cachedir / "cache" / "xul__iris.symc"
    file4.write_bytes(b"ab")

    # Access rose so it's recently used
    file1.read_bytes()

    # Run events and verify LRU
    cm.run_once()
    assert cm.lru == {str(file1): 2, str(file2): 2, str(file3): 2, str(file4): 2}
    assert cm.total_size == 8

    # Add new file which will evict files--but not rose which was accessed
    # most recently
    file5 = cachedir / "cache" / "xul__marigold.symc"
    file5.write_bytes(b"abcdef")
    cm.run_once()
    assert cm.lru == {str(file1): 2, str(file4): 2, str(file5): 6}
    assert cm.total_size == 10

    # Verify what's in the cache dir on disk
    files = [str(path) for path in (cachedir / "cache").iterdir()]
    assert sorted(files) == sorted([str(file1), str(file4), str(file5)])


def test_add_file(cm_client, tmpdir):
    cachedir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(cachedir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager
    cm.run_once()
    assert cm.lru == {}

    file1 = cachedir / "cache" / "file1.symc"
    file1.write_bytes(b"abcde")
    cm.run_once()
    assert cm.lru == {str(file1): 5}


def test_delete_file(cm_client, tmpdir):
    cachedir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(cachedir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager
    cm.run_once()

    file1 = cachedir / "cache" / "file1.symc"
    file1.write_bytes(b"abcde")
    cm.run_once()
    assert cm.lru == {str(file1): 5}

    file1.unlink()
    cm.run_once()
    assert cm.lru == {}


def test_moved_to(cm_client, tmpdir):
    cachedir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(cachedir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager

    cm.run_once()
    assert cm.lru == {}
    assert cm.total_size == 0

    file1 = cachedir / "cache" / "file1.symc"
    file1.write_bytes(b"abcde")
    cm.run_once()
    assert cm.lru == {str(file1): 5}
    assert cm.total_size == 5

    dest_file1 = cachedir / "cache" / "file1_copied.symc"
    file1.rename(dest_file1)
    cm.run_once()
    assert cm.lru == {str(dest_file1): 5}
    assert cm.total_size == 5

    # NOTE(willkg): This is in the cachedir, but not the part watched by the cache
    # manager
    file3 = cachedir / "file3.symc"
    file3.write_bytes(b"abc")
    cm.run_once()
    assert cm.lru == {str(dest_file1): 5}
    assert cm.total_size == 5

    dest_file3 = cachedir / "cache" / "file3.symc"
    file3.rename(dest_file3)
    cm.run_once()
    assert cm.lru == {str(dest_file1): 5, str(dest_file3): 3}
    assert cm.total_size == 8


def test_moved_from(cm_client, tmpdir):
    cachedir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(cachedir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager

    cm.run_once()
    assert cm.lru == {}
    assert cm.total_size == 0

    file1 = cachedir / "cache" / "file1.symc"
    file1.write_bytes(b"abcde")
    cm.run_once()
    assert cm.lru == {str(file1): 5}
    assert cm.total_size == 5

    dest_file1 = cachedir / "file1.symc"
    file1.rename(dest_file1)
    cm.run_once()
    assert cm.lru == {}
    assert cm.total_size == 0


def test_nested_directories(cm_client, tmpdir):
    cachedir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(cachedir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager

    cm.run_once()
    assert cm.lru == {}

    dir1 = cachedir / "cache" / "dir1"
    dir1.mkdir()

    # Run to pick up the new subdirectory and watch it
    cm.run_once()

    subdir1 = dir1 / "subdir1"
    subdir1.mkdir()

    # Run to pick up the new subsubdirectory and watch it
    cm.run_once()

    # Create two files in the subsubdirectory with 9 bytes
    file1 = subdir1 / "file1.symc"
    file1.write_bytes(b"abcde")

    file2 = subdir1 / "file2.symc"
    file2.write_bytes(b"abcd")

    cm.run_once()
    assert cm.lru == {str(file1): 5, str(file2): 4}

    # Add a new file with 2 bytes that puts it over the edge
    file3 = dir1 / "file3.symc"
    file3.write_bytes(b"ab")

    cm.run_once()
    assert cm.lru == {str(file2): 4, str(file3): 2}
