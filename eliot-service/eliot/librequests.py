# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Utilities for using the requests library.
"""

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, ReadTimeout
from urllib3.util.retry import (
    ConnectTimeoutError,
    ProtocolError,
    ProxyError,
    ReadTimeoutError,
)


# Exceptions that indicate an HTTP request should be retried
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    ConnectTimeoutError,
    ProtocolError,
    ProxyError,
    ReadTimeout,
    ReadTimeoutError,
)


class HTTPAdapterWithTimeout(HTTPAdapter):
    """HTTPAdapter with a default timeout

    This allows you to set a default timeout when creating the adapter.
    It can be overridden here as well as when doing individual
    requests.

    :arg varies default_timeout: number of seconds before timing out

        This can be a float or a (connect timeout, read timeout) tuple
        of floats.

        Defaults to 5.0 seconds.

    """

    def __init__(self, *args, **kwargs):
        self._default_timeout = kwargs.pop("default_timeout", 5.0)
        super().__init__(*args, **kwargs)

    def send(self, *args, **kwargs):
        # If there's a timeout, use that. Otherwise, use the default.
        kwargs["timeout"] = kwargs.get("timeout") or self._default_timeout
        return super().send(*args, **kwargs)


def requests_session(default_timeout=5.0):
    """Returns session that has a default timeout

    :arg varies default_timeout: number of seconds before timing out

        This can be a float or a (connect timeout, read timeout) tuple
        of floats.

    :returns: a requests Session instance

    """
    session = requests.Session()

    # Set the User-Agent header so we can distinguish our stuff from other stuff
    session.headers.update({"User-Agent": "tecken-requests/1.0"})

    adapter = HTTPAdapterWithTimeout(default_timeout=default_timeout)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session
