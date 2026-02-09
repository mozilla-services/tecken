# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import shlex
import site
import subprocess
from unittest.mock import ANY

from fillmore.test import diff_structure
import requests
from werkzeug.test import Client

from django.contrib.auth.models import User

from obs_common.sentry_wrap import get_release_name
from tecken.apps import count_sentry_scrub_error
from tecken.tokens.models import Token
from tecken.wsgi import application


[SITE_PACKAGES] = site.getsitepackages()

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
                            "abs_path": SITE_PACKAGES
                            + "/django/core/handlers/exception.py",
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
                            "abs_path": SITE_PACKAGES + "/django/core/handlers/base.py",
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
    "transaction_info": {"source": ANY},
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

        (event,) = sentry_client.envelope_payloads

        # Drop the "_meta" bit because we don't want to compare that.
        del event["_meta"]

        differences = diff_structure(event, BROKEN_EVENT)
        assert differences == []


def test_count_sentry_scrub_error(metricsmock):
    metricsmock.clear_records()
    count_sentry_scrub_error("foo")
    metricsmock.assert_incr(
        "tecken.sentry_scrub_error", value=1, tags=["host:testnode"]
    )


def test_sentry_wrap_non_app_error_has_release():
    fakesentry_url = "http://fakesentry:8090/"

    # Flush fakesentry to ensure we fetch only the desired error downstream
    requests.post(f"{fakesentry_url}api/flush/")

    expected_release = get_release_name()

    # Pass a non-Django command that will error to sentry-wrap
    non_app_command = "ls -2"
    sentry_wrap_command = f"sentry-wrap wrap-process -- {non_app_command}"
    cmd_args = shlex.split(sentry_wrap_command)
    subprocess.run(cmd_args, timeout=10)

    # We don't have to worry about a race condition here, because when the
    # subprocess exits, we know the sentry_sdk sent the event, and it has
    # been processed successfully by fakesentry.
    events_resp = requests.get(f"{fakesentry_url}api/eventlist/")
    events_resp.raise_for_status()
    event_id = events_resp.json()["events"][0]["event_id"]
    event_resp = requests.get(f"{fakesentry_url}api/event/{event_id}")
    event_resp.raise_for_status()

    release = event_resp.json()["payload"]["envelope_header"]["trace"]["release"]

    assert release == expected_release
