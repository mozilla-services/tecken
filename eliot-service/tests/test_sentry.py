# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
from unittest.mock import ANY

from werkzeug.test import Client

from eliot.app import get_app


# NOTE(willkg): If this changes, we should update it and look for new things that should
# be scrubbed. Use ANY for things that change between tests.
BROKEN_EVENT = {
    "level": "error",
    "exception": {
        "values": [
            {
                "module": None,
                "type": "Exception",
                "value": "intentional exception",
                "mechanism": {"type": "logging", "handled": True},
                "stacktrace": {
                    "frames": [
                        {
                            "filename": "falcon/app.py",
                            "abs_path": "/app/eliot-service/falcon/app.py",
                            "function": "falcon.app.App.__call__",
                            "module": "falcon.app",
                            "lineno": ANY,
                            "pre_context": [],
                            "context_line": None,
                            "post_context": [],
                            "vars": {
                                "__name__": "'falcon.app'",
                                "__doc__": "'Falcon App class.'",
                                "__package__": "'falcon'",
                                "__loader__": ANY,
                                "__spec__": ANY,
                                "__file__": ANY,
                                "__builtins__": "<module 'builtins' (built-in)>",
                                "wraps": ANY,
                                "iscoroutinefunction": ANY,
                                "re": ANY,
                            },
                            "in_app": True,
                        },
                        {
                            "filename": "eliot/health_resource.py",
                            "abs_path": "/app/eliot-service/eliot/health_resource.py",
                            "function": "on_get",
                            "module": "eliot.health_resource",
                            "lineno": ANY,
                            "pre_context": ANY,
                            "context_line": ANY,
                            "post_context": ANY,
                            "vars": {
                                "self": ANY,
                                "req": "<Request: GET 'http://localhost/__broken__'>",
                                "resp": "<Response: 200 OK>",
                            },
                            "in_app": True,
                        },
                    ]
                },
            }
        ]
    },
    "logger": "eliot.app",
    "logentry": {"message": "Unhandled exception", "params": []},
    "extra": {
        "host_id": "testcode",
        "processname": "tests",
        "asctime": ANY,
        "sys.argv": ANY,
    },
    "event_id": ANY,
    "timestamp": ANY,
    "breadcrumbs": ANY,
    "contexts": {
        "runtime": {
            "name": "CPython",
            "version": ANY,
            "build": ANY,
        }
    },
    "modules": ANY,
    "release": ANY,
    "environment": "production",
    "server_name": "testnode",
    "sdk": {
        "name": "sentry.python",
        "version": "1.5.12",
        "packages": [{"name": "pypi:sentry-sdk", "version": "1.5.12"}],
        "integrations": [
            "argv",
            "atexit",
            "dedupe",
            "excepthook",
            "falcon",
            "logging",
            "modules",
            "stdlib",
            "threading",
        ],
    },
    "platform": "python",
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
        print(json.dumps(event, indent=4))

        assert event == BROKEN_EVENT
