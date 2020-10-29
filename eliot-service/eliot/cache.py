# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
Contains LRU disk cache code for symc files.
"""

import logging
from pathlib import Path
import re
import tempfile

import markus


LOGGER = logging.getLogger(__name__)
METRICS = markus.get_metrics(__name__)


NO_DEFAULT = object()


class DiskCache:
    """Disk cache of symcache files.

    NOTE(willkg): This sets and checks the cache--it doesn't do any cleanup. The Disk
    Cache Manager watches the disk and enforces a max size by evicting least recently
    used files. That way you can have multiple Eliot processes and a single Disk Cache
    Manager running on the same node.

    """

    # NOTE(willkg): this puts all files in the same directory--no directory trees
    BAD_CHARS = re.compile(r"[^A-Za-z0-9._-]")

    def __init__(self, cachedir, tmpdir):
        """
        :arg Path cachedir: location for cache--should already exist
        :arg Path tmpdir: location for temp files--should already exist
        """
        self.cachedir = cachedir
        self.tmpdir = tmpdir

    def key_to_filepath(self, key):
        """Sanitize a key and convert to a filepath.

        :arg str key: cache key

        :returns: sanitized Path

        """
        # NOTE(willkg): we want to make sure we sanitize the file path in a way that
        # doesn't allow two different valid keys to end up as the same file.

        # Remove / and . at the beginning
        key = key.lstrip("/.")

        # Replace all non-good characters with _
        key = self.BAD_CHARS.sub("_", key)

        filepath = self.cachedir / Path(key)
        return filepath

    def __contains__(self, key):
        """Returns whether this key exists.

        This lets you use the Python "in" operator.

        :arg str key: the key to retrieve for

        :returns: bool

        """
        filepath = self.key_to_filepath(key)
        return filepath.exists()

    def get(self, key, default=NO_DEFAULT):
        """Retrieve contents for a given key.

        :arg str key: the key to retrieve for
        :arg bytes default: the default to return if there's no key; otherwise this
            raises a KeyError

        :returns: data as bytes

        :raises KeyError: if there's no key and no default is given

        """
        filepath = self.key_to_filepath(key)
        if filepath.is_file():
            try:
                with filepath.open(mode="rb") as fp:
                    data = fp.read()
                    METRICS.incr("diskcache.cache_hit")
                    return data
            except (OSError, IOError):
                METRICS.incr("diskcache.read_error")
                LOGGER.exception("Cache error on read")

        METRICS.incr("diskcache.cache_miss")
        if default != NO_DEFAULT:
            return default
        raise KeyError(f"key {filepath!r} does not exist")

    def set(self, key, data):
        """Set contents for a given key.

        This will log and emit metrics on OSError and IOError.

        :arg str key: the key to set
        :arg bytes data: the data to save

        """
        filepath = self.key_to_filepath(key)

        # Save the file to a temp file and then rename that so as to avoid race
        # conditions.
        try:
            temp_fp = tempfile.NamedTemporaryFile(
                mode="w+b", suffix=".sym", dir=self.tmpdir, delete=False
            )
            temp_fp.write(data)
            temp_fp.close()

            filepath.parent.mkdir(parents=True, exist_ok=True)
            Path(temp_fp.name).rename(filepath)

        except (IOError, OSError):
            LOGGER.exception("Exception when writing to disk cache")
            METRICS.incr("diskcache.write_error")
