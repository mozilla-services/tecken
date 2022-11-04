# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
from unittest.mock import ANY

from markus.testing import MetricsMock
from werkzeug.test import Client

from django.contrib.auth.models import User

from tecken.apps import count_sentry_scrub_error
from tecken.tokens.models import Token
from tecken.wsgi import application


# NOTE(willkg): If this changes, we should update it and look for new things that should
# be scrubbed. Use ANY for things that change between tests like timestamps, source code
# data (line numbers, file names, post/pre_context), event ids, build ids, versions,
# etc.
BROKEN_EVENT = {
    "breadcrumbs": {
        "values": [
            {
                "category": "query",
                "data": {},
                "message": (
                    'SELECT "tokens_token"."id", "tokens_token"."user_id", '
                    + '"tokens_token"."key", "tokens_token"."expires_at", '
                    + '"tokens_token"."notes", "tokens_token"."created_at", '
                    + '"auth_user"."id", "auth_user"."password", '
                    + '"auth_user"."last_login", "auth_user"."is_superuser", '
                    + '"auth_user"."username", "auth_user"."first_name", '
                    + '"auth_user"."last_name", "auth_user"."email", '
                    + '"auth_user"."is_staff", "auth_user"."is_active", '
                    + '"auth_user"."date_joined" FROM "tokens_token" INNER JOIN '
                    + '"auth_user" ON ("tokens_token"."user_id" = "auth_user"."id") '
                    + 'WHERE "tokens_token"."key" = %s LIMIT 21'
                ),
                "timestamp": ANY,
                "type": "default",
            },
            {
                "category": "query",
                "data": {},
                "message": 'UPDATE "auth_user" SET "last_login" = %s WHERE "auth_user"."id" = %s',
                "timestamp": ANY,
                "type": "default",
            },
        ]
    },
    "contexts": {
        "runtime": {
            "build": ANY,
            "name": "CPython",
            "version": ANY,
        },
        "trace": {
            "description": "sentry_sdk.integrations.django._got_request_exception",
            "op": "event.django",
            "parent_span_id": ANY,
            "span_id": ANY,
            "trace_id": ANY,
        },
    },
    "environment": "production",
    "event_id": ANY,
    "exception": {
        "values": [
            {
                "mechanism": {"handled": False, "type": "django"},
                "module": None,
                "stacktrace": {
                    "frames": [
                        {
                            "abs_path": "/usr/local/lib/python3.9/site-packages/django/core/handlers/exception.py",
                            "context_line": ANY,
                            "filename": "django/core/handlers/exception.py",
                            "function": "inner",
                            "in_app": True,
                            "lineno": ANY,
                            "module": "django.core.handlers.exception",
                            "post_context": ANY,
                            "pre_context": ANY,
                            "vars": {
                                "exc": "Exception('Intentional exception')",
                                "get_response": ANY,
                                "request": "[Scrubbed]",
                            },
                        },
                        {
                            "abs_path": "/usr/local/lib/python3.9/site-packages/django/core/handlers/base.py",
                            "context_line": ANY,
                            "filename": "django/core/handlers/base.py",
                            "function": "_get_response",
                            "in_app": True,
                            "lineno": ANY,
                            "module": "django.core.handlers.base",
                            "post_context": ANY,
                            "pre_context": ANY,
                            "vars": {
                                "callback": ANY,
                                "callback_args": [],
                                "callback_kwargs": {},
                                "request": "[Scrubbed]",
                                "response": "None",
                                "self": ANY,
                                "wrapped_callback": ANY,
                            },
                        },
                        {
                            "abs_path": "/app/tecken/views.py",
                            "context_line": ANY,
                            "filename": "tecken/views.py",
                            "function": "broken_view",
                            "in_app": True,
                            "lineno": ANY,
                            "module": "tecken.views",
                            "post_context": ANY,
                            "pre_context": ANY,
                            "vars": {"request": "[Scrubbed]"},
                        },
                    ]
                },
                "type": "Exception",
                "value": "Intentional exception",
            }
        ]
    },
    "extra": {"sys.argv": ANY},
    "level": "error",
    "modules": ANY,
    "platform": "python",
    "release": ANY,
    "request": {
        "data": "[Scrubbed]",
        "env": {"SERVER_NAME": "localhost", "SERVER_PORT": "80"},
        "headers": {
            "Auth-Token": "[Scrubbed]",
            "Content-Length": ANY,
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "localhost",
            "X-Forwarded-For": "[Scrubbed]",
            "X-Real-Ip": "[Scrubbed]",
        },
        "method": "GET",
        "query_string": "code=%5BScrubbed%5D&state=%5BScrubbed%5D",
        "url": "http://localhost/__broken__",
    },
    "sdk": {
        "integrations": [
            "argv",
            "atexit",
            "boto3",
            "dedupe",
            "django",
            "excepthook",
            "logging",
            "modules",
            "redis",
            "stdlib",
            "threading",
        ],
        "name": "sentry.python.django",
        "packages": [{"name": "pypi:sentry-sdk", "version": ANY}],
        "version": ANY,
    },
    "server_name": ANY,
    "timestamp": ANY,
    "transaction": "/__broken__",
    "transaction_info": {"source": "route"},
}


def test_sentry_scrubbing(sentry_helper, transactional_db):
    """Test sentry scrubbing configuration

    This verifies that the scrubbing configuration is working by using the /__broken__
    view to trigger an exception that causes Sentry to emit an event for.

    This also helps us know when something has changed when upgrading sentry_sdk that
    would want us to update our scrubbing code or sentry init options.

    This test will fail whenever we:

    * update sentry_sdk to a new version
    * update Django to a new version that somehow adjusts the callstack for an
      exception happening in view code

    In those cases, we should copy the new event, read through it for new problems, and
    redact the parts that will change using ANY so it passes tests.

    """
    client = Client(application)

    # Create a user and a token so the token is valid
    user = User.objects.create(username="francis", email="francis@example.com")
    token = Token.objects.create(user=user)

    with sentry_helper.reuse() as sentry_client:
        resp = client.get(
            "/__broken__",
            query_string={"code": "codeabcde", "state": "stateabcde"},
            headers=[
                ("Auth-Token", token.key),
                ("X-Forwarded-For", "forabcde"),
                ("X-Real-Ip", "forip"),
            ],
            data={
                "csrfmiddlewaretoken": "csrfabcde",
                "client_secret": "clientabcde",
            },
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
        metricsmock.assert_incr("tecken.sentry_scrub_error", value=1)
