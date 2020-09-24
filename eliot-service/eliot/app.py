# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import logging.config
from pathlib import Path

from everett.manager import ConfigManager, ConfigOSEnv
from everett.component import ConfigOptions, RequiredConfigMixin
import falcon

from eliot.health_resource import (
    BrokenResource,
    HeartbeatResource,
    LBHeartbeatResource,
    VersionResource,
)
from eliot.index_resource import IndexResource
from eliot.logginglib import setup_logging, log_config
from eliot.markuslib import setup_metrics
from eliot.sentrylib import (
    set_sentry_client,
    setup_sentry_logging,
    wsgi_capture_exceptions,
)
from eliot.symbolicate_resource import SymbolicateV4, SymbolicateV5


LOGGER = logging.getLogger(__name__)
REPOROOT_DIR = str(Path(__file__).parent.parent.parent)


def build_config_manager():
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


class AppConfig(RequiredConfigMixin):
    """Application-level config.

    To pull out a config item, you can do this::

        config = ConfigManager([ConfigOSEnv()])
        app_config = AppConfig(config)

        debug = app_config('debug')


    To create a component with configuration, you can do this::

        class SomeComponent(RequiredConfigMixin):
            required_config = ConfigOptions()

            def __init__(self, config):
                self.config = config.with_options(self)

        some_component = SomeComponent(app_config.config)


    To pass application-level configuration to components, you should do it
    through arguments like this::

        class SomeComponent(RequiredConfigMixin):
            required_config = ConfigOptions()

            def __init__(self, config, debug):
                self.config = config.with_options(self)
                self.debug = debug

        some_component = SomeComponent(app_config.config_manager, debug)

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
            "middleware will be used instead. "
            "See https://docs.sentry.io/quickstart/#configure-the-dsn for details."
        ),
    )

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.config = config_manager.with_options(self)

    def __call__(self, key):
        """Return configuration for given key."""
        return self.config(key)

    def verify_configuration(self):
        # Access each configuration key which will force it to evaluate and kick up an
        # error if it's busted.
        for key, opt in self.required_config.options.items():
            self.config(key)


class EliotAPI(falcon.API):
    """Falcon API for Eliot."""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._all_resources = {}

    def setup(self):
        # Set up logging and sentry first, so we have something to log to. Then
        # build and log everything else.
        setup_logging(self.config)
        LOGGER.info("Repository root: %s", REPOROOT_DIR)
        set_sentry_client(self.config("secret_sentry_dsn"), REPOROOT_DIR)

        # Log application configuration
        log_config(LOGGER, self.config)

        # Set up Sentry exception logger if we're so configured
        setup_sentry_logging()
        setup_metrics(self.config, LOGGER)

        self.add_route("version", "/__version__", VersionResource(REPOROOT_DIR))
        self.add_route("heartbeat", "/__heartbeat__", HeartbeatResource(self))
        self.add_route("lbheartbeat", "/__lbheartbeat__", LBHeartbeatResource())
        self.add_route("broken", "/__broken__", BrokenResource())

        self.add_route("index", "/", IndexResource())
        self.add_route("symbolicate_v4", "/symbolicate/v4", SymbolicateV4())
        self.add_route("symbolicate_v5", "/symbolicate/v5", SymbolicateV5())

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
    """Return EliotAPI instance."""
    if config_manager is None:
        config_manager = build_config_manager()

    app_config = AppConfig(config_manager)
    app_config.verify_configuration()

    # Build the app
    app = EliotAPI(app_config)

    # Set the app up and verify setup
    app.setup()
    app.verify()

    # Wrap the app in some kind of unhandled exception notification mechanism
    app = wsgi_capture_exceptions(app)

    if app_config("local_dev_env"):
        LOGGER.info("Eliot is running! http://localhost:8050")

    return app
