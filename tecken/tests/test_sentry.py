# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import time
from unittest.mock import ANY, patch

from fillmore.test import diff_event
import requests
from werkzeug.test import Client

from django.contrib.auth.models import User

from tecken.apps import count_sentry_scrub_error
from tecken.tokens.models import Token
from tecken.wsgi import application
from bin.sentry_wrap import wrap_process


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
                "module": "tecken.views",
                "stacktrace": {
                    "frames": [
                        {
                            "abs_path": "/usr/local/lib/python3.11/site-packages/django/core/handlers/exception.py",
                            "context_line": ANY,
                            "filename": "django/core/handlers/exception.py",
                            "function": "inner",
                            "in_app": False,
                            "lineno": ANY,
                            "module": "django.core.handlers.exception",
                            "post_context": ANY,
                            "pre_context": ANY,
                            "vars": {
                                "exc": "IntentionalException()",
                                "get_response": ANY,
                                "request": "[Scrubbed]",
                            },
                        },
                        {
                            "abs_path": "/usr/local/lib/python3.11/site-packages/django/core/handlers/base.py",
                            "context_line": ANY,
                            "filename": "django/core/handlers/base.py",
                            "function": "_get_response",
                            "in_app": False,
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
                "type": "IntentionalException",
                "value": "",
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

        differences = diff_event(event, BROKEN_EVENT)
        assert differences == []


def test_count_sentry_scrub_error(metricsmock):
    metricsmock.clear_records()
    count_sentry_scrub_error("foo")
    metricsmock.assert_incr(
        "tecken.sentry_scrub_error", value=1, tags=["host:testnode"]
    )


@patch("bin.sentry_wrap.get_release_name")
def test_sentry_wrap_non_app_error_has_release(mock_get_release_name):
    port = os.environ.get("EXPOSE_SENTRY_PORT", 8090)

    # Flush fakesentry to ensure we fetch only the desired error downstream
    requests.post(f"http://fakesentry:{port}/api/flush/")

    release = "123:456"
    mock_get_release_name.return_value = release

    expected_event = {"release": release}

    # Pass a non-Django command that will error to sentry_wrap
    cmd = "ls -2"
    wrap_process([cmd], standalone_mode=False)

    # TODO: Wait until condition: the next request has non-empty `errors` in resp.json()
    time.sleep(1)
    errors_resp = requests.get(f"http://fakesentry:{port}/api/errorlist/")
    errors_resp.raise_for_status()
    error_id = errors_resp.json()["errors"][0]
    error_resp = requests.get(f"http://fakesentry:{port}/api/error/{error_id}")
    error_resp.raise_for_status()
    actual_event = error_resp.json()["payload"]

    assert actual_event["release"] == expected_event["release"]
