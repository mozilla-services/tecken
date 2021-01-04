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
    return DiskCacheManagerTestClient(get_cache_manager(config_manager))


def test_setup_with_no_files_has_empty_lru(cm_client):
    assert len(cm_client.cache_manager.lru) == 0
    assert cm_client.cache_manager.total_size == 0


def test_setup_with_files(cm_client, tmpdir):
    pathlib.Path(tmpdir / "xul__ABCDE.symc").write_bytes(b"abcde")
    pathlib.Path(tmpdir / "xul__01234.symc").write_bytes(b"abcdef")

    # Rebuild with the tmpdir we're using
    cm_client.rebuild({"ELIOT_SYMBOLS_CACHE_DIR": str(tmpdir)})

    assert len(cm_client.cache_manager.lru) == 2
    assert cm_client.cache_manager.total_size == 11


def test_addfiles(cm_client, tmpdir):
    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(tmpdir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager
    try:
        cm.run_once()

        # We've got a fresh cache manager with nothing in it
        assert cm.lru == {}
        assert cm.total_size == 0

        # Add one 5-byte file and run loop and make sure it's in the LRU
        file1 = pathlib.Path(tmpdir / "xul__5byte.symc")
        file1.write_bytes(b"abcde")
        cm.run_once()
        assert cm.lru == {str(file1): 5}
        assert cm.total_size == 5

        # Add one 4-byte file and run loop and now we've got two files in the LRU
        file2 = pathlib.Path(tmpdir / "xul__4byte.symc")
        file2.write_bytes(b"abcd")
        cm.run_once()
        assert cm.lru == {str(file1): 5, str(file2): 4}
        assert cm.total_size == 9

    finally:
        cm.shutdown()
        del cm


def test_eviction_when_too_big(cm_client, tmpdir):
    tmpdir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(tmpdir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager
    try:
        cm.run_once()

        # We've got a fresh cache manager with nothing in it
        assert cm.lru == {}
        assert cm.total_size == 0

        # Add one 5-byte file and run loop and make sure it's in the LRU
        file1 = tmpdir / "xul__5byte.symc"
        file1.write_bytes(b"abcde")

        # Add one 4-byte file and run loop and now we've got two files in the LRU
        file2 = tmpdir / "xul__4byte.symc"
        file2.write_bytes(b"abcd")
        cm.run_once()
        assert cm.lru == {str(file1): 5, str(file2): 4}
        assert cm.total_size == 9

        # Add 1-byte file which gets total size to 10
        file3 = tmpdir / "xul__3byte.symc"
        file3.write_bytes(b"a")
        cm.run_once()
        assert cm.lru == {str(file1): 5, str(file2): 4, str(file3): 1}
        assert cm.total_size == 10

        # Add file4 of 6 bytes should evict file1 and file2
        file4 = tmpdir / "xul__6byte.symc"
        file4.write_bytes(b"abcdef")
        cm.run_once()
        assert cm.lru == {str(file3): 1, str(file4): 6}
        assert cm.total_size == 7

        # Verify what's in the cache dir on disk
        files = [str(path) for path in tmpdir.iterdir()]
        assert sorted(files) == sorted([str(file3), str(file4)])
    finally:
        cm.shutdown()


def test_eviction_of_least_recently_used(cm_client, tmpdir):
    tmpdir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(tmpdir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )

    cm = cm_client.cache_manager
    try:
        cm.run_once()

        # We've got a fresh cache manager with nothing in it
        assert cm.lru == {}
        assert cm.total_size == 0

        # Add some files
        file1 = tmpdir / "xul__rose.symc"
        file1.write_bytes(b"ab")

        file2 = tmpdir / "xul__dandelion.symc"
        file2.write_bytes(b"ab")

        file3 = tmpdir / "xul__orchid.symc"
        file3.write_bytes(b"ab")

        file4 = tmpdir / "xul__iris.symc"
        file4.write_bytes(b"ab")

        # Access rose so it's recently used
        file1.read_bytes()

        # Run events and verify LRU
        cm.run_once()
        assert cm.lru == {str(file1): 2, str(file2): 2, str(file3): 2, str(file4): 2}
        assert cm.total_size == 8

        # Add new file which will evict files--but not rose which was accessed
        # most recently
        file5 = tmpdir / "xul__marigold.symc"
        file5.write_bytes(b"abcdef")
        cm.run_once()
        assert cm.lru == {str(file1): 2, str(file4): 2, str(file5): 6}
        assert cm.total_size == 10

        # Verify what's in the cache dir on disk
        files = [str(path) for path in tmpdir.iterdir()]
        assert sorted(files) == sorted([str(file1), str(file4), str(file5)])
    finally:
        cm.shutdown()
