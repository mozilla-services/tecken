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
import time

import msgpack
import msgpack.exceptions

from eliot.libmarkus import METRICS


LOGGER = logging.getLogger(__name__)


NO_DEFAULT = object()


class CacheReadError(Exception):
    """Exception for errors hit when reading the cache from disk"""


class DiskCache:
    """Disk cache of msgpack data files

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
        :arg Path tmpdir: location for temporary files
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

        .. Note::

           This doesn't guarantee that the item can be read from cache without error.

        :arg str key: the key to retrieve for

        :returns: bool

        """
        filepath = self.key_to_filepath(key)
        return filepath.exists()

    def read_from_file(self, filepath):
        """Reads data from a file

        This reads from a file, unpacks it and returns the data.

        :arg Path filepath: the file to read from

        :returns: data as dict

        :raises CacheReadError: if there's a problem reading from the cache file
            or unpacking it

        """
        try:
            with filepath.open("rb") as fp:
                data = fp.read()

            return msgpack.unpackb(data)

        except (OSError, msgpack.exceptions.ExtraData):
            raise CacheReadError(f"can't read {filepath} from cache")

    def write_to_file(self, filepath, data):
        """Write data to a file

        This converts the data to msgpack then saves it to disk. It tries to account for
        race conditions between reads and writes by writing to a temporary file and then
        renaming it.

        :arg Path filepath: the file to write to
        :arg dict data: the data to write

        :returns: True if successful, False if there was a problem

        """
        # Pack the data into a single blob
        data = msgpack.packb(data)

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
            return True

        except OSError:
            LOGGER.exception("Exception when writing to disk cache")
            return False

    def get(self, key, default=NO_DEFAULT):
        """Retrieve contents for a given key.

        :arg str key: the key to retrieve for
        :arg bytes default: the default to return if there's no key; otherwise this
            raises a KeyError

        :returns: data as dict

        :raises KeyError: if there's no key or there's an error when reading from
            cache and no default is given

        """
        error = False
        start_time = time.perf_counter()
        filepath = self.key_to_filepath(key)
        if filepath.is_file():
            try:
                data = self.read_from_file(filepath)

                delta = (time.perf_counter() - start_time) * 1000.0
                METRICS.histogram(
                    "eliot.diskcache.get", value=delta, tags=["result:hit"]
                )
                return data
            except CacheReadError:
                error = True
                LOGGER.exception("Cache error on read")

        delta = (time.perf_counter() - start_time) * 1000.0
        METRICS.histogram(
            "eliot.diskcache.get",
            value=delta,
            tags=["result:" + ("error" if error else "miss")],
        )
        if default != NO_DEFAULT:
            return default
        raise KeyError(f"key {filepath!r} not in cache")

    def set(self, key, data):
        """Set contents for a given key.

        This will log and emit metrics on OSError and IOError.

        :arg str key: the key to set
        :arg dict data: the data to save as a key/val dict

        """
        assert isinstance(data, dict)

        start_time = time.perf_counter()
        filepath = self.key_to_filepath(key)

        ret = self.write_to_file(filepath, data)
        result = "success" if ret else "fail"

        delta = (time.perf_counter() - start_time) * 1000.0
        METRICS.histogram("eliot.diskcache.set", value=delta, tags=["result:" + result])
