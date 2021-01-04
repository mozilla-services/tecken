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

    $ python eliot/cache_manager.py

"""

from collections import OrderedDict
import logging
import os
import pathlib
import sys
import traceback

import click
from everett.component import ConfigOptions, RequiredConfigMixin
import inotify_simple
from inotify_simple import flags

from eliot.app import build_config_manager
from eliot.liblogging import setup_logging, log_config
from eliot.libmarkus import setup_metrics, METRICS
from eliot.libsentry import set_sentry_client, setup_sentry_logging


if __name__ == "__main__":
    MODULE_NAME = "eliot.cache_manager"
else:
    MODULE_NAME = __name__


LOGGER = logging.getLogger(MODULE_NAME)
REPOROOT_DIR = str(pathlib.Path(__file__).parent.parent.parent)


def handle_exception(exctype, value, tb):
    LOGGER.error(
        "Unhandled exception. Exiting.\n"
        + "".join(traceback.format_exception(exctype, value, tb))
    )


sys.excepthook = handle_exception


class AppConfig(RequiredConfigMixin):
    """Application-level config.

    Defines configuration needed for Eliot disk cache manager and convenience methods
    for accessing it.

    """

    required_config = ConfigOptions()
    required_config.add_option(
        "local_dev_env",
        default="False",
        parser=bool,
        doc="Whether or not this is a local development environment.",
        alternate_keys=["root:local_dev_env"],
    )
    required_config.add_option(
        "host_id",
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
    required_config.add_option(
        "logging_level",
        default="INFO",
        doc="The logging level to use. DEBUG, INFO, WARNING, ERROR or CRITICAL",
    )
    required_config.add_option(
        "statsd_host", default="localhost", doc="Hostname for statsd server."
    )
    required_config.add_option(
        "statsd_port", default="8124", doc="Port for statsd server.", parser=int
    )
    required_config.add_option(
        "statsd_namespace", default="", doc="Namespace for statsd metrics."
    )
    required_config.add_option(
        "secret_sentry_dsn",
        default="",
        doc=(
            "Sentry DSN to use. If this is not set an unhandled exception logging "
            "middleware will be used instead.\n\n"
            "See https://docs.sentry.io/quickstart/#configure-the-dsn for details."
        ),
    )
    required_config.add_option(
        "symbols_cache_dir",
        default="/tmp/cache",
        doc="Location for caching symcache files.",
    )
    required_config.add_option(
        "symbols_cache_max_size",
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

    def __call__(self, key):
        """Return configuration for given key."""
        return self.config(key)

    def verify_configuration(self):
        """Verify configuration by accessing each item

        This will raise a configuration error if something isn't right.

        """
        for key, opt in self.required_config.options.items():
            self.config(key)


class DiskCacheManager:
    def __init__(self, config):
        self.config = config
        self.cache_dir = pathlib.Path(self.config("symbols_cache_dir")).resolve()
        self.max_size = self.config("symbols_cache_max_size")

        self.total_size = 0
        self.lru = OrderedDict()
        self._generator = None

    def setup(self):
        setup_logging(self.config, processname="cache_manager")
        setup_metrics(self.config)

        set_sentry_client(self.config("secret_sentry_dsn"), str(REPOROOT_DIR))
        setup_sentry_logging()

        log_config(LOGGER, self.config)

        # If there's no cache dir, we can't watch anything, so create it
        if not self.cache_dir.is_dir():
            self.cache_dir.mkdir(exist_ok=True)

        LOGGER.info(
            f"DiskCacheManager starting up; watching: {self.cache_dir}, max size: {self.max_size:,d}"
        )

        self.inventory_existing()

        LOGGER.info(f"Found {len(self.lru)} files ({self.total_size:,d} bytes)")

    def mark_access(self, path):
        """Mark a file access in the bookkeeping.

        :arg Path path: path of the file that was accessed

        """
        lru_key = str(path)
        if lru_key in self.lru and path.exists():
            self.lru.move_to_end(lru_key, last=True)
            return

    def mark_remove(self, path):
        """Mark a file remove in the bookkeeping.

        NOTE(willkg): The most commont reason a file is removed is because it was
        evicted.

        :arg Path path: path of the file that was removed

        """
        lru_key = str(path)
        if lru_key in self.lru:
            size = self.lru.pop(lru_key)
            self.total_size -= size

    def update_bookkeeping(self, path):
        """Update bookkeeping for a specified path.

        :arg Path path: the path of the file to update in our bookkeeping

        """
        lru_key = str(path)

        # If the path is in the cache, remove it
        if lru_key in self.lru:
            size = self.lru.pop(lru_key)
            self.total_size -= size
            LOGGER.debug(f"removed {path} {size:,d}")

        # If the path exists, calculate new total size, check max size, remove items,
        # and re-add path.
        if path.exists():
            size = path.stat().st_size
            self.total_size += size

            # If we're beyond the max, then we need to evict items to size down as much
            # as we can
            while self.lru and self.total_size > self.max_size:
                rm_path, rm_size = self.lru.popitem(last=False)
                rm_path = pathlib.Path(rm_path)
                self.total_size -= rm_size
                rm_path.unlink(missing_ok=True)
                LOGGER.debug(f"evicted {rm_path} {rm_size:,d}")
                METRICS.incr("eliot.diskcache.evict")

            # Since the file exists, add it to the lru
            LOGGER.debug(f"added {path} {size:,d}")
            self.lru[lru_key] = size

        LOGGER.debug(f"lru: count {len(self.lru)}, size {self.total_size:,d}")

    def inventory_existing(self):
        """Walk cache_dir directory and update bookkeeping."""
        # Reset everything
        self.total_size = 0
        self.lru = OrderedDict()

        # Walk directory and update bookkeeping
        for base, dirs, files in os.walk(str(self.cache_dir)):
            for fn in files:
                fn = os.path.join(base, fn)
                self.update_bookkeeping(pathlib.Path(fn))

    def _event_generator(self, nonblocking=False):
        """Returns a generator of inotify events."""
        if nonblocking:
            # NOTE(willkg): Timeout of 0 should return immediately if there's nothing
            # there
            timeout = 0
        else:
            timeout = 1000

        inotify = inotify_simple.INotify(nonblocking=nonblocking)
        watch_flags = (
            flags.ACCESS
            | flags.CREATE
            | flags.DELETE
            | flags.MODIFY
            | flags.MOVED_FROM
            | flags.MOVED_TO
        )
        watch_descriptor = inotify.add_watch(str(self.cache_dir), watch_flags)

        LOGGER.info("Entering loop")
        self.running = True
        try:
            while self.running:
                for event in inotify.read(timeout=timeout):
                    LOGGER.debug(event)
                    event_flags = flags.from_mask(event.mask)
                    # Ignore changes to directories
                    if flags.ISDIR in event_flags:
                        continue

                    path = self.cache_dir / event.name
                    if flags.CREATE in event_flags:
                        self.process_create(path, event)
                    elif flags.MOVED_FROM in event_flags:
                        self.process_moved_from(path, event)
                    elif flags.MOVED_TO in event_flags:
                        self.process_moved_to(path, event)
                    elif flags.MODIFY in event_flags:
                        self.process_modify(path, event)
                    elif flags.DELETE in event_flags:
                        self.process_delete(path, event)
                    elif flags.ACCESS in event_flags:
                        self.process_access(path, event)
                    else:
                        LOGGER.debug(f"ignored {path} {event}")

                yield

        finally:
            inotify.rm_watch(watch_descriptor)

        inotify.close()

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

    def process_delete(self, path, event):
        """Process a delete event."""
        LOGGER.debug(f"delete {path}")
        self.mark_remove(path)

    def process_create(self, path, event):
        """Process a delete event."""
        LOGGER.debug(f"create {path}")
        self.update_bookkeeping(path)

    def process_moved_from(self, path, event):
        """Process a moved_from event."""
        LOGGER.debug(f"moved_from {path}")
        self.mark_remove(path)

    def process_moved_to(self, path, event):
        """Process a moved_to event."""
        LOGGER.debug(f"moved_to {path}")
        self.update_bookkeeping(path)

    def process_modify(self, path, event):
        """Process a modify event."""
        LOGGER.debug(f"modify {path}")
        self.update_bookkeeping(path)

    def process_access(self, path, event):
        """Process an access event."""
        LOGGER.debug(f"access {path}")
        self.mark_access(path)


def get_cache_manager(config_manager=None):
    """Create and return a DiskCacheManager."""
    if config_manager is None:
        config_manager = build_config_manager()

    app_config = AppConfig(config_manager)
    app_config.verify_configuration()

    manager = DiskCacheManager(app_config)
    return manager


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

    cache_manager.setup()
    cache_manager.run_loop()


if __name__ == "__main__":
    main()
