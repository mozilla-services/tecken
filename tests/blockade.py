"""
This blocks all HTTP requests via httplib (which includes requests).

This is an adjusted version of pytest-blockage. We're calling it blockade.

Original code: https://pypi.org/project/pytest-blockage/
License: MIT https://github.com/rob-b/pytest-blockage/blob/master/LICENSE

"""

import http.client as httplib
import logging


logger = logging.getLogger(__name__)


class MockHttpCall(Exception):
    pass


class MockSmtpCall(Exception):
    pass


def block_http(allow):
    def allowed(self, host, *args, **kwargs):
        try:
            string_type = basestring
        except NameError:
            # python3
            string_type = str
        if isinstance(host, string_type) and host not in allow:
            logger.warning("Denied HTTP connection to: %s" % host)
            raise MockHttpCall(host)
        logger.debug("Allowed HTTP connection to: %s" % host)
        return self.old(host, *args, **kwargs)

    allowed.blockade = True

    if not getattr(httplib.HTTPConnection, "blockade", False):
        logger.debug("Monkey patching httplib")
        httplib.HTTPConnection.old = httplib.HTTPConnection.__init__
        httplib.HTTPConnection.__init__ = allowed


def pytest_addoption(parser):
    group = parser.getgroup("blockade")
    group.addoption(
        "--blockade", action="store_true", help="Block network requests during test run"
    )

    parser.addini("blockade", "Block network requests during test run", default=False)

    group.addoption(
        "--blockade-http-allow",
        action="store",
        help="Do not block HTTP requests to this comma separated list of " "hostnames",
        default="",
    )
    parser.addini(
        "blockade-http-allow",
        "Do not block HTTP requests to this comma separated list of hostnames",
        default="",
    )


def pytest_sessionstart(session):
    config = session.config
    if config.option.blockade or config.getini("blockade"):
        http_allow_str = config.option.blockade_http_allow or config.getini(
            "blockade-http-allow"
        )
        http_allow = http_allow_str.split(",")
        block_http(http_allow)
