# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
This defines the DiskCacheManager application. It's designed to run as
a standalone application separate from the rest of Eliot which is a webapp.

It keeps track of files in a directory and evicts files least recently
used in order to keep the total size under a max number.

It uses inotify to cheaply watch the files.

Configuration is in AppConfig and set in environment variables.

To run::

    $ /app/bin/run_eliot_disk_manager.sh

"""

from collections import OrderedDict
import logging
import os
import pathlib
import sys
import traceback

from boltons.dictutils import OneToOne
import click
from everett.manager import get_config_for_class, Option
from inotify_simple import INotify, flags

from eliot.app import build_config_manager
from eliot.liblogging import setup_logging, log_config
from eliot.libmarkus import setup_metrics, METRICS
from eliot.libsentry import setup_sentry_logging


if __name__ == "__main__":
    MODULE_NAME = "eliot.cache_manager"
else:
    MODULE_NAME = __name__


LOGGER = logging.getLogger(MODULE_NAME)
REPOROOT_DIR = str(pathlib.Path(__file__).parent.parent.parent)
MAX_ERRORS = 10


class LastUpdatedOrderedDict(OrderedDict):
    """Store items in the order the keys were last added or updated"""

    def __setitem__(self, key, value):
        """Create or update a key"""
        super().__setitem__(key, value)
        self.move_to_end(key, last=True)

    def touch(self, key):
        """Update last-updated for key"""
        self.move_to_end(key, last=True)

    def popoldest(self):
        """Pop the oldest item"""
        return self.popitem(last=False)


def handle_exception(exctype, value, tb):
    LOGGER.error(
        "unhandled exception. Exiting.\n"
        + "".join(traceback.format_exception(exctype, value, tb))
    )


sys.excepthook = handle_exception


class DiskCacheManager:
    class Config:
        local_dev_env = Option(
            default="False",
            parser=bool,
            doc="Whether or not this is a local development environment.",
            alternate_keys=["root:local_dev_env"],
        )
        host_id = Option(
            default="",
            doc=(
                "Identifier for the host that is running Eliot. This identifies "
                "this Eliot instance in the logs and makes it easier to correlate "
                "Eliot logs with other data. For example, the value could be a "
                "public hostname, an instance id, or something like that. If you do not "
                "set this, then socket.gethostname() is used instead."
            ),
            alternate_keys=["root:host_id"],
        )
        logging_level = Option(
            default="INFO",
            doc="The logging level to use. DEBUG, INFO, WARNING, ERROR or CRITICAL",
        )
        statsd_host = Option(default="localhost", doc="Hostname for statsd server.")
        statsd_port = Option(default="8124", doc="Port for statsd server.", parser=int)
        statsd_namespace = Option(default="", doc="Namespace for statsd metrics.")
        secret_sentry_dsn = Option(
            default="",
            doc=(
                "Sentry DSN to use. If this is not set an unhandled exception logging "
                "middleware will be used instead.\n\n"
                "See https://docs.sentry.io/quickstart/#configure-the-dsn for details."
            ),
        )
        symbols_cache_dir = Option(
            default="/tmp/cache",
            doc="Location for caching symcache files.",
        )
        symbols_cache_max_size = Option(
            default=str(1024 * 1024 * 1024),
            parser=int,
            doc=(
                "Max size (bytes) of symbols cache. You can use _ to group digits for "
                "legibility."
            ),
        )

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.config = config_manager.with_options(self)

        # NOTE(willkg): This needs to mirror setup of cachedir in Eliot app
        self.cachedir = (
            pathlib.Path(self.config("symbols_cache_dir")).resolve() / "cache"
        )
        self.max_size = self.config("symbols_cache_max_size")

        # Set up attributes for cache monitoring; these get created in the generator
        self.lru = LastUpdatedOrderedDict()
        self.total_size = 0
        self.watches = OneToOne()
        self._generator = None
        self.inotify = None
        self.watch_flags = (
            flags.ACCESS
            | flags.CREATE
            | flags.DELETE
            | flags.DELETE_SELF
            | flags.MODIFY
            | flags.MOVED_FROM
            | flags.MOVED_TO
        )

    def setup(self):
        setup_logging(
            logging_level=self.config("logging_level"),
            debug=self.config("local_dev_env"),
            host_id=self.config("host_id"),
            processname="cache_manager",
        )
        setup_metrics(
            statsd_host=self.config("statsd_host"),
            statsd_port=self.config("statsd_port"),
            statsd_namespace=self.config("statsd_namespace"),
            debug=self.config("local_dev_env"),
        )

        setup_sentry_logging(
            basedir=str(REPOROOT_DIR),
            host_id=self.config("host_id"),
            sentry_dsn=self.config("secret_sentry_dsn"),
        )

        log_config(LOGGER, self.config, self)

        # Create the cachedir if we need to
        self.cachedir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            f"starting up; watching: {self.cachedir}, max size: {self.max_size:,d}"
        )

    def verify_configuration(self):
        """Verify configuration by accessing each item

        This will raise a configuration error if something isn't right.

        """
        for key, val in get_config_for_class(self.__class__).items():
            self.config(key)

    def add_watch(self, path):
        wd = self.inotify.add_watch(path, self.watch_flags)
        self.watches[path] = wd

    def remove_watch(self, path):
        if path in self.watches:
            del self.watches[path]

    def inventory_existing(self):
        """Sets up LRU from cachedir

        This goes through the cachedir and adds watches for directories and adds files
        to the LRU.

        NOTE(willkg): this does not deal with the max size of the LRU--that'll get
        handled when we start going through events.

        """
        cachedir = str(self.cachedir)

        self.add_watch(cachedir)
        for base, dirs, files in os.walk(cachedir):
            for dir_ in dirs:
                path = os.path.join(base, dir_)
                self.add_watch(path)
                LOGGER.debug(f"adding watch: {path}")

            for fn in files:
                path = os.path.join(base, fn)
                size = os.stat(path).st_size
                self.lru[path] = size
                self.total_size += size
                LOGGER.debug(f"adding file: {path} ({size:,d})")

    def make_room(self, size):
        total_size = self.total_size + size
        removed = 0

        while self.lru and total_size > self.max_size:
            rm_path, rm_size = self.lru.popoldest()
            total_size -= rm_size
            removed += rm_size
            os.remove(rm_path)
            LOGGER.debug(f"evicted {rm_path} {rm_size:,d}")
            METRICS.incr("eliot.diskcache.evict")

        self.total_size -= removed

    def _event_generator(self, nonblocking=False):
        """Returns a generator of inotify events."""
        if nonblocking:
            # NOTE(willkg): Timeout of 0 should return immediately if there's nothing
            # there
            timeout = 0
        else:
            timeout = 1000

        self.inotify = INotify(nonblocking=nonblocking)

        # Set up watches and LRU with what exists already
        self.watches = OneToOne()
        self.lru = LastUpdatedOrderedDict()
        self.total_size = 0
        self.inventory_existing()

        LOGGER.info(f"found {len(self.lru)} files ({self.total_size:,d} bytes)")

        LOGGER.info("entering loop")
        self.running = True
        processed_events = False
        num_unhandled_errors = 0
        try:
            while self.running:
                try:
                    for event in self.inotify.read(timeout=timeout):
                        processed_events = True
                        event_flags = flags.from_mask(event.mask)

                        flags_list = ", ".join([str(flag) for flag in event_flags])
                        LOGGER.debug(f"EVENT: {event}: {flags_list}")

                        if flags.IGNORED in event_flags:
                            continue

                        dir_path = self.watches.inv[event.wd]
                        path = os.path.join(dir_path, event.name)

                        if flags.ISDIR in event_flags:
                            # Handle directory events which update our watch lists
                            if flags.CREATE in event_flags:
                                self.add_watch(path)

                            if flags.DELETE_SELF in event_flags:
                                if path in self.watches:
                                    self.remove_watch(path)

                        else:
                            # Handle file events which update our LRU cache
                            if flags.CREATE in event_flags:
                                if path not in self.lru:
                                    size = os.stat(path).st_size
                                    self.make_room(size)
                                    self.lru[path] = size
                                    self.total_size += size

                            elif flags.ACCESS in event_flags:
                                if path in self.lru:
                                    self.lru.touch(path)

                            elif flags.MODIFY in event_flags:
                                size = self.lru[path]
                                new_size = os.stat(path).st_size
                                if size != new_size:
                                    self.total_size -= size
                                    self.make_room(new_size)
                                    self.total_size += new_size

                                self.lru[path] = new_size

                            elif flags.DELETE in event_flags:
                                if path in self.lru:
                                    # NOTE(willkg): DELETE can be triggered by an
                                    # external thing or by the disk cache manager, so it
                                    # may or may not be in the lru
                                    size = self.lru.pop(path)
                                    self.total_size -= size

                            elif flags.MOVED_TO in event_flags:
                                if path not in self.lru:
                                    # If the path isn't in self.lru, then treat this
                                    # like a create
                                    size = os.stat(path).st_size
                                    self.make_room(size)
                                    self.lru[path] = size
                                    self.total_size += size

                            elif flags.MOVED_FROM in event_flags:
                                if path in self.lru:
                                    # If it was moved out of this directory, then treat
                                    # it like a DELETE
                                    size = self.lru.pop(path)
                                    self.total_size -= size

                            else:
                                LOGGER.debug(f"ignored {path} {event}")

                except Exception:
                    LOGGER.exception("Exception thrown while handling events.")

                    # If there are more than 10 unhandled errors, it's probably
                    # something seriously wrong and the loop should terminate
                    num_unhandled_errors += 1
                    if num_unhandled_errors >= MAX_ERRORS:
                        LOGGER.error("Exceeded maximum number of errors.")
                        raise

                if processed_events:
                    LOGGER.debug(
                        f"lru: count {len(self.lru)}, size {self.total_size:,d}"
                    )
                    METRICS.gauge("eliot.diskcache.usage", value=self.total_size)
                    processed_events = False

                yield

        finally:
            all_watches = list(self.watches.inv.keys())
            for wd in all_watches:
                try:
                    self.inotify.rm_watch(wd)
                except Exception:
                    # We're ending the loop, so if there's some exception, we should
                    # print it but move on.
                    LOGGER.exception("Exception thrown while removing watches")

        self.inotify.close()

    def run_loop(self):
        """Run cache manager in a loop."""
        if self._generator is None:
            self._generator = self._event_generator()

        while True:
            next(self._generator)

        self.shutdown()

    def run_once(self):
        """Runs a nonblocking event generator once."""
        if self._generator is None:
            self._generator = self._event_generator(nonblocking=True)

        return next(self._generator)

    def shutdown(self):
        """Shut down an event generator."""
        if self._generator:
            # Stop the generator loop
            self.running = False
            generator = self._generator
            self._generator = None
            try:
                # Run the generator one more time so it exits the loop and closes
                # the FileIO
                next(generator)
            except StopIteration:
                pass


def get_cache_manager(config_manager=None):
    """Create and return a DiskCacheManager."""
    if config_manager is None:
        config_manager = build_config_manager()

    return DiskCacheManager(config_manager)


@click.command(help="See https://tecken.readthedocs.io/en/latest/symbolication.html")
@click.option(
    "--print-config/--no-print-config",
    default=False,
    help="Print configuration and exit.",
)
def main(print_config):
    cache_manager = get_cache_manager()
    if print_config:
        click.echo("Run-time configuration:")

        class ClickEchoLogger:
            def info(self, text):
                click.echo(text)

        log_config(ClickEchoLogger(), cache_manager.config)
        return

    cache_manager.verify_configuration()
    cache_manager.setup()
    cache_manager.run_loop()


if __name__ == "__main__":
    main()
