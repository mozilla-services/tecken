# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
import pathlib
from unittest.mock import ANY

from everett.manager import ConfigManager, ConfigDictEnv, ConfigOSEnv
import pytest

from eliot.cache_manager import get_cache_manager, LastUpdatedOrderedDict


class TestLastUpdatedOrderedDict:
    def test_set(self):
        lru = LastUpdatedOrderedDict()

        lru["key1"] = 1
        lru["key2"] = 2
        assert list(lru.items()) == [("key1", 1), ("key2", 2)]

        lru["key1"] = 3
        assert list(lru.items()) == [("key2", 2), ("key1", 3)]

    def test_touch(self):
        lru = LastUpdatedOrderedDict()

        lru["key1"] = 1
        lru["key2"] = 2

        lru.touch("key1")
        assert list(lru.items()) == [("key2", 2), ("key1", 1)]

    def test_popoldest(self):
        lru = LastUpdatedOrderedDict()

        lru["key1"] = 1
        lru["key2"] = 2

        oldest = lru.popoldest()
        assert oldest == ("key1", 1)
        assert list(lru.items()) == [("key2", 2)]


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


# NOTE(willkg): If this changes, we should update it and look for new things that should
# be scrubbed. Use ANY for things that change between tests.
BROKEN_EVENT = {
    "level": "error",
    "exception": {
        "values": [
            {
                "module": None,
                "type": "Exception",
                "value": "intentional exception",
                "mechanism": {
                    "type": "logging",
                    "handled": True,
                },
                "stacktrace": {
                    "frames": [
                        {
                            "filename": "eliot/cache_manager.py",
                            "abs_path": "/app/eliot-service/eliot/cache_manager.py",
                            "function": "_event_generator",
                            "module": "eliot.cache_manager",
                            "lineno": 293,
                            "pre_context": ANY,
                            "context_line": ANY,
                            "post_context": ANY,
                            "vars": {
                                "self": ANY,
                                "nonblocking": "True",
                                "timeout": "0",
                                "processed_events": "True",
                                "num_unhandled_errors": "0",
                                "event": ["1", "256", "0", "'xul__4byte.symc'"],
                                "event_flags": ["<flags.CREATE: 256>"],
                                "flags_list": "'flags.CREATE'",
                                "dir_path": ANY,
                                "path": ANY,
                            },
                            "in_app": True,
                        },
                        {
                            "filename": "tests/test_cache_manager.py",
                            "abs_path": "/app/eliot-service/tests/test_cache_manager.py",
                            "function": "mock_make_room",
                            "module": "tests.test_cache_manager",
                            "lineno": ANY,
                            "pre_context": ANY,
                            "context_line": ANY,
                            "post_context": ANY,
                            "vars": {"args": ["4"], "kwargs": {}},
                            "in_app": True,
                        },
                    ]
                },
            }
        ]
    },
    "logger": "eliot.cache_manager",
    "logentry": {"message": "Exception thrown while handling events.", "params": []},
    "extra": {
        "host_id": "testcode",
        "processname": "tests",
        "asctime": ANY,
        "sys.argv": ANY,
    },
    "event_id": ANY,
    "timestamp": ANY,
    "breadcrumbs": ANY,
    "contexts": {
        "runtime": {
            "name": "CPython",
            "version": ANY,
            "build": ANY,
        }
    },
    "modules": ANY,
    "release": "none:unknown",
    "environment": "production",
    "server_name": "testnode",
    "sdk": {
        "name": "sentry.python",
        "version": "1.5.12",
        "packages": [{"name": "pypi:sentry-sdk", "version": "1.5.12"}],
        "integrations": [
            "argv",
            "atexit",
            "dedupe",
            "excepthook",
            "logging",
            "modules",
            "stdlib",
            "threading",
        ],
    },
    "platform": "python",
}


def test_sentry_scrubbing(sentry_helper, cm_client, monkeypatch, tmpdir):
    """Test sentry scrubbing configuration

    This verifies that the scrubbing configuration is working by using the /__broken__
    view to trigger an exception that causes Sentry to emit an event for.

    This also helps us know when something has changed when upgrading sentry_sdk that
    would want us to update our scrubbing code or sentry init options.

    This test will fail whenever we:

    * update sentry_sdk to a new version
    * update configuration which will changing the logging breadcrumbs

    In those cases, we should copy the new event, read through it for new problems, and
    redact the parts that will change using ANY so it passes tests.

    """
    cachedir = pathlib.Path(tmpdir)

    # Rebuild with the tmpdir we're using
    cm_client.rebuild(
        {
            "ELIOT_SYMBOLS_CACHE_DIR": str(cachedir),
            "ELIOT_SYMBOLS_CACHE_MAX_SIZE": 10,
        }
    )
    cm = cm_client.cache_manager

    with sentry_helper.reuse() as sentry_client:
        # Mock out "make_room" so we can force the cache manager to raise an exception in
        # the area it might raise a real exception
        def mock_make_room(*args, **kwargs):
            raise Exception("intentional exception")

        monkeypatch.setattr(cm, "make_room", mock_make_room)

        # Add some files to trigger the make_room call
        file1 = cachedir / "cache" / "xul__5byte.symc"
        file1.write_bytes(b"abcde")
        cm.run_once()
        file2 = cachedir / "cache" / "xul__4byte.symc"
        file2.write_bytes(b"abcd")
        cm.run_once()

        (event,) = sentry_client.events

        # Drop the "_meta" bit because we don't want to compare that.
        del event["_meta"]

        # If this test fails, this will print out the new event that you can copy and
        # paste and then edit above
        print(json.dumps(event, indent=4))

        assert event == BROKEN_EVENT
