# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
from pathlib import Path
import sys

from everett.manager import ConfigManager, ConfigDictEnv, ConfigOSEnv
from falcon.request import Request
from falcon.testing.helpers import create_environ
from falcon.testing.client import TestClient
import markus
from markus.testing import MetricsMock
import pytest
import requests_mock
import shutil

# Add the eliot project root to sys.path, otherwise tests can't find it
SYMROOT = str(Path(__file__).parent.parent)
sys.path.insert(0, SYMROOT)

from eliot.app import get_app  # noqa
from eliot.liblogging import setup_logging  # noqa


def pytest_runtest_setup(item):
    # Clear out the tmp and cache dir from any sym files before tests run
    cachedir = os.environ["ELIOT_SYMBOLS_CACHE_DIR"]

    if os.path.exists(cachedir):
        shutil.rmtree(cachedir, ignore_errors=True)


def pytest_collection_finish(session):
    # After pytest test collection has finished, make sure we set up logging and metrics
    # to sensible default values.
    setup_logging(
        logging_level="DEBUG",
        debug=True,
        host_id="testcode",
        processname="tests",
    )
    markus.configure([{"class": "markus.backends.logging.LoggingMetrics"}])


@pytest.fixture
def request_generator():
    """Returns a Falcon Request generator"""

    def _request_generator(method, path, query_string=None, headers=None, body=None):
        env = create_environ(
            method=method,
            path=path,
            query_string=(query_string or ""),
            headers=headers,
            body=body,
        )
        return Request(env)

    return _request_generator


class EliotTestClient(TestClient):
    """Test client to ease testing with Eliot API"""

    @classmethod
    def build_config(cls, new_config=None):
        """Build ConfigManager using environment and overrides."""
        new_config = new_config or {}
        config_manager = ConfigManager(
            environments=[ConfigDictEnv(new_config), ConfigOSEnv()]
        )
        return config_manager.with_namespace("eliot")

    def rebuild_app(self, new_config=None):
        """Rebuilds the app

        This is helpful if you've changed configuration and need to rebuild the
        app so that components pick up the new configuration.

        :arg new_config: dict of configuration to override normal values to build the
            new app with

        """
        self.app = get_app(self.build_config(new_config))

    def get_resource_by_name(self, name):
        """Retrieves the Falcon API resource by name"""
        # NOTE(willkg): The "app" here is a middleware which should have an .application
        # attribute which is the actual EliotApp that we want.
        return self.app.application.get_resource_by_name(name)


@pytest.fixture
def client():
    """Test client for the Eliot API

    This creates an app and a test client that uses that app to submit HTTP
    GET/POST requests.

    The app that's created uses configuration defaults. If you need it to use
    an app with a different configuration, you can rebuild the app with
    different configuration::

        def test_foo(client, tmpdir):
            client.rebuild_app({
                "HOST_ID": "foo"
            })

    """
    return EliotTestClient(get_app(EliotTestClient.build_config()))


@pytest.fixture
def metricsmock():
    """Returns MetricsMock that a context to record metrics records

    Usage::

        def test_something(metricsmock):
            with metricsmock as mm:
                # do stuff
                assert mm.has_record(
                    stat='some.stat',
                    kwargs_contains={
                        'something': 1
                    }
                )

    """
    return MetricsMock()


@pytest.fixture
def requestsmock():
    with requests_mock.Mocker() as m:
        yield m


@pytest.fixture
def tmpcachedir(tmpdir):
    """Yield a temp cache dir.

    pytest generates a tmpdir for the test, so tmpcachedir ends up being a subdirectory
    of tmpdir.

    """
    cachedir = tmpdir / "cache"
    Path(cachedir).mkdir(parents=True, exist_ok=True)
    yield cachedir
