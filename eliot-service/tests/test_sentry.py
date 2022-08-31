# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
from unittest.mock import ANY

from markus.testing import MetricsMock
from werkzeug.test import Client

from eliot.app import get_app, count_sentry_scrub_error


# NOTE(willkg): If this changes, we should update it and look for new things that should
# be scrubbed. Use ANY for things that change between tests.
BROKEN_EVENT = {
    "breadcrumbs": {
        "values": [
            {
                "category": "markus",
                "data": {"asctime": ANY, "host_id": "testcode", "processname": "tests"},
                "level": "info",
                "message": ANY,
                "timestamp": ANY,
                "type": "log",
            }
        ]
    },
    "contexts": {
        "runtime": {
            "build": ANY,
            "name": "CPython",
            "version": ANY,
        },
        "trace": {
            "description": None,
            "op": "http.server",
            "parent_span_id": None,
            "span_id": ANY,
            "trace_id": ANY,
        },
    },
    "environment": "production",
    "event_id": ANY,
    "exception": {
        "values": [
            {
                "mechanism": {"handled": False, "type": "eliot"},
                "module": None,
                "stacktrace": {
                    "frames": [
                        {
                            "abs_path": "/app/eliot-service/falcon/app.py",
                            "context_line": ANY,
                            "filename": "falcon/app.py",
                            "function": "falcon.app.App.__call__",
                            "in_app": True,
                            "lineno": ANY,
                            "module": "falcon.app",
                            "post_context": ANY,
                            "pre_context": ANY,
                            "vars": {
                                "__builtins__": "<module 'builtins' (built-in)>",
                                "__doc__": "'Falcon App class.'",
                                "__file__": ANY,
                                "__loader__": ANY,
                                "__name__": "'falcon.app'",
                                "__package__": "'falcon'",
                                "__spec__": ANY,
                                "iscoroutinefunction": ANY,
                                "re": "<module 're' from '/usr/local/lib/python3.9/re.py'>",
                                "wraps": ANY,
                            },
                        },
                        {
                            "abs_path": "/app/eliot-service/eliot/health_resource.py",
                            "context_line": ANY,
                            "filename": "eliot/health_resource.py",
                            "function": "on_get",
                            "in_app": True,
                            "lineno": ANY,
                            "module": "eliot.health_resource",
                            "post_context": ANY,
                            "pre_context": ANY,
                            "vars": {
                                "req": "<Request: GET 'http://localhost/__broken__'>",
                                "resp": "<Response: 200 OK>",
                                "self": ANY,
                            },
                        },
                    ]
                },
                "type": "Exception",
                "value": "intentional exception",
            }
        ]
    },
    "extra": {"sys.argv": ANY},
    "level": "error",
    "modules": ANY,
    "platform": "python",
    "release": ANY,
    "request": {
        "env": {"SERVER_NAME": "localhost", "SERVER_PORT": "80"},
        "headers": {
            "Host": "localhost",
            "X-Forwarded-For": "[Scrubbed]",
            "X-Real-Ip": "[Scrubbed]",
        },
        "method": "GET",
        "query_string": "",
        "url": "http://localhost/__broken__",
    },
    "sdk": {
        "integrations": [
            "argv",
            "atexit",
            "dedupe",
            "excepthook",
            "logging",
            "modules",
            "stdlib",
            "threading",
        ],
        "name": "sentry.python",
        "packages": [{"name": "pypi:sentry-sdk", "version": "1.9.5"}],
        "version": "1.9.5",
    },
    "server_name": "testnode",
    "timestamp": ANY,
    "transaction": "/__broken__",
    "transaction_info": {},
}


def test_sentry_scrubbing(sentry_helper):
    """Test sentry scrubbing configuration

    This verifies that the scrubbing configuration is working by using the /__broken__
    view to trigger an exception that causes Sentry to emit an event for.

    This also helps us know when something has changed when upgrading sentry_sdk that
    would want us to update our scrubbing code or sentry init options.

    This test will fail whenever we:

    * update sentry_sdk to a new version
    * update Falcon to a new version that somehow adjusts the callstack for an exception
      happening in view code
    * update configuration which will changing the logging breadcrumbs

    In those cases, we should copy the new event, read through it for new problems, and
    redact the parts that will change using ANY so it passes tests.

    """
    client = Client(get_app())

    with sentry_helper.reuse() as sentry_client:
        resp = client.get(
            "/__broken__",
            headers=[
                ("X-Forwarded-For", "forabcde"),
                ("X-Real-Ip", "forip"),
            ],
        )
        assert resp.status_code == 500

        (event,) = sentry_client.events

        # Drop the "_meta" bit because we don't want to compare that.
        del event["_meta"]

        # If this test fails, this will print out the new event that you can copy and
        # paste and then edit above
        print(json.dumps(event, indent=4, sort_keys=True))

        assert event == BROKEN_EVENT


def test_count_sentry_scrub_error():
    with MetricsMock() as metricsmock:
        metricsmock.clear_records()
        count_sentry_scrub_error("foo")
        metricsmock.assert_incr(
            "eliot.sentry_scrub_error", value=1, tags=["service:webapp"]
        )
