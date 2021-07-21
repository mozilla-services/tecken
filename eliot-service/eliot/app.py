# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
Holds the EliotApp code. EliotApp is a WSGI app implemented using Falcon.
"""

import logging
import logging.config
from pathlib import Path

from everett.manager import (
    ConfigManager,
    ConfigOSEnv,
    get_config_for_class,
    ListOf,
    Option,
)
import falcon

from eliot.cache import DiskCache
from eliot.downloader import SymbolFileDownloader
from eliot.health_resource import (
    BrokenResource,
    HeartbeatResource,
    LBHeartbeatResource,
    VersionResource,
)
from eliot.index_resource import IndexResource
from eliot.liblogging import setup_logging, log_config
from eliot.libmarkus import setup_metrics
from eliot.libsentry import (
    set_sentry_client,
    setup_sentry_logging,
    wsgi_capture_exceptions,
)
from eliot.symbolicate_resource import SymbolicateV4, SymbolicateV5


LOGGER = logging.getLogger(__name__)
REPOROOT_DIR = str(Path(__file__).parent.parent.parent)


def build_config_manager():
    """Build and return an Everett ConfigManager

    :returns: everett.ConfigManager

    """
    config = ConfigManager(
        environments=[
            # Pull configuration from environment variables
            ConfigOSEnv()
        ],
        doc=(
            "For configuration help, see "
            "https://tecken.readthedocs.io/en/latest/symbolicator.html"
        ),
    )
    return config.with_namespace("eliot")


class AppConfig:
    """Application-level config.

    Defines configuration needed for Eliot and convenience methods for accessing it.

    """

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
                "middleware will be used instead. "
                "See https://docs.sentry.io/quickstart/#configure-the-dsn for details."
            ),
        )
        symbols_cache_dir = Option(
            default="/tmp/cache",
            doc="Location for caching symcache files.",
        )
        symbols_urls = Option(
            default="https://symbols.mozilla.org/try/",
            doc="Comma-separated list of urls to pull symbols files from.",
            parser=ListOf(str),
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
        for key, val in get_config_for_class(self.__class__).items():
            self.config(key)


class EliotApp(falcon.App):
    """Falcon App for Eliot."""

    def __init__(self, config):
        cors_middleware = falcon.CORSMiddleware(
            allow_origins="*",
            expose_headers=[
                "accept",
                "accept-encoding",
                "authorization",
                "content-type",
                "dnt",
                "origin",
                "user-agent",
                "x-csrftoken",
                "x-requested-with",
            ],
        )

        super().__init__(middleware=cors_middleware)
        self.config = config
        self._all_resources = {}

    def setup(self):
        # Set up logging and sentry first, so we have something to log to. Then
        # build and log everything else.
        setup_logging(
            logging_level=self.config("logging_level"),
            debug=self.config("local_dev_env"),
            host_id=self.config("host_id"),
            processname="webapp",
        )
        LOGGER.info("Repository root: %s", REPOROOT_DIR)
        set_sentry_client(self.config("secret_sentry_dsn"), REPOROOT_DIR)

        # Log application configuration
        log_config(LOGGER, self.config)

        # Set up Sentry exception logger if we're so configured
        setup_sentry_logging()
        setup_metrics(
            statsd_host=self.config("statsd_host"),
            statsd_port=self.config("statsd_port"),
            statsd_namespace=self.config("statsd_namespace"),
            debug=self.config("local_dev_env"),
        )

        # Set up cachedir and tmpdir
        cachedir = Path(self.config("symbols_cache_dir")).resolve()
        cachecachedir = cachedir / "cache"
        cachecachedir.mkdir(parents=True, exist_ok=True)
        tmpdir = cachedir / "tmp"
        tmpdir.mkdir(parents=True, exist_ok=True)

        self.add_route("version", "/__version__", VersionResource(REPOROOT_DIR))
        self.add_route("heartbeat", "/__heartbeat__", HeartbeatResource())
        self.add_route("lbheartbeat", "/__lbheartbeat__", LBHeartbeatResource())
        self.add_route("broken", "/__broken__", BrokenResource())

        diskcache = DiskCache(cachedir=cachecachedir, tmpdir=tmpdir)
        downloader = SymbolFileDownloader(self.config("symbols_urls"))
        self.add_route("index", "/", IndexResource())
        self.add_route(
            "symbolicate_v4",
            "/symbolicate/v4",
            SymbolicateV4(downloader=downloader, cache=diskcache, tmpdir=tmpdir),
        )
        self.add_route(
            "symbolicate_v5",
            "/symbolicate/v5",
            SymbolicateV5(downloader=downloader, cache=diskcache, tmpdir=tmpdir),
        )

    def add_route(self, name, uri_template, resource, *args, **kwargs):
        """Add specified Falcon route.

        :arg str name: friendly name for this route; use alphanumeric characters

        :arg str url_template: Falcon url template for this route

        :arg obj resource: Falcon resource to handl this route

        """
        self._all_resources[name] = resource
        super().add_route(uri_template, resource, *args, **kwargs)

    def get_resource_by_name(self, name):
        """Return registered resource with specified name.

        :arg str name: the name of the resource to get

        :raises KeyError: if there is no resource by that name

        """
        return self._all_resources[name]

    def get_resources(self):
        """Return a list of registered resources."""
        return self._all_resources.values()

    def verify(self):
        """Verify that Eliot is ready to start."""


def get_app(config_manager=None):
    """Build and return EliotApp instance.

    :arg config_manager: Everet ConfigManager to use; if None, it will build one

    :returns: EliotApp instance

    """
    if config_manager is None:
        config_manager = build_config_manager()

    app_config = AppConfig(config_manager)
    app_config.verify_configuration()

    # Create the app and verify configuration
    app = EliotApp(app_config)
    app.setup()
    app.verify()

    # Wrap the app in some kind of unhandled exception notification mechanism
    app = wsgi_capture_exceptions(app)

    if app_config("local_dev_env"):
        LOGGER.info("Eliot is running! http://localhost:8050")

    return app
