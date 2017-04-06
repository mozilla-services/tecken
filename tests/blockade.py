"""
This blocks all HTTP requests via httplib (which includes requests).

this is a fixed copy of pytest-blockage, called "blockade"
"""
import logging
import sys

if sys.version_info[0] < 3:
    import httplib
else:
    import http.client as httplib


logger = logging.getLogger(__name__)


class MockHttpCall(Exception):
    pass


class MockSmtpCall(Exception):
    pass


def block_http(whitelist):
    def whitelisted(self, host, *args, **kwargs):
        try:
            string_type = basestring
        except NameError:
            # python3
            string_type = str
        if isinstance(host, string_type) and host not in whitelist:
            logger.warning('Denied HTTP connection to: %s' % host)
            raise MockHttpCall(host)
        logger.debug('Allowed HTTP connection to: %s' % host)
        return self.old(host, *args, **kwargs)

    whitelisted.blockade = True

    if not getattr(httplib.HTTPConnection, 'blockade', False):
        logger.debug('Monkey patching httplib')
        httplib.HTTPConnection.old = httplib.HTTPConnection.__init__
        httplib.HTTPConnection.__init__ = whitelisted


def pytest_addoption(parser):
    group = parser.getgroup('blockade')
    group.addoption('--blockade', action='store_true',
                    help='Block network requests during test run')

    parser.addini(
        'blockade', 'Block network requests during test run', default=False)

    group.addoption(
        '--blockade-http-whitelist',
        action='store',
        help='Do not block HTTP requests to this comma separated list of '
             'hostnames',
        default=''
    )
    parser.addini(
        'blockade-http-whitelist',
        'Do not block HTTP requests to this comma separated list of hostnames',
        default=''
    )


def pytest_sessionstart(session):
    config = session.config
    if config.option.blockade or config.getini('blockade'):
        http_whitelist_str = (
            config.option.blockade_http_whitelist or
            config.getini('blockade-http-whitelist')
        )
        http_whitelist = http_whitelist_str.split(',')
        block_http(http_whitelist)
