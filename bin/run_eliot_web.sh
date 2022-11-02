#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# default variables
: "${ELIOT_GUNICORN_PORT:=8000}"
: "${ELIOT_GUNICORN_WORKERS:=1}"
: "${ELIOT_GUNICORN_TIMEOUT:=300}"
: "${ELIOT_GUNICORN_CMD_PREFIX:=}"
: "${ELIOT_GUNICORN_MAX_REQUESTS:=0}"
: "${ELIOT_GUNICORN_MAX_REQUESTS_JITTER:=0}"

# NOTE(willkg): overrides for memory problem situation--these are temporary
# stopgap values. bug #1793984
ELIOT_GUNICORN_MAX_REQUESTS=750
ELIOT_GUNICORN_MAX_REQUESTS_JITTER=100
ELIOT_GUNICORN_WORKERS=5

(set -o posix; set) | grep ELIOT_GUNICORN

cd /app/eliot-service/

${ELIOT_GUNICORN_CMD_PREFIX} gunicorn \
    --bind 0.0.0.0:"${ELIOT_GUNICORN_PORT}" \
    --timeout "${ELIOT_GUNICORN_TIMEOUT}" \
    --workers "${ELIOT_GUNICORN_WORKERS}" \
    --max-requests="${ELIOT_GUNICORN_MAX_REQUESTS}" \
    --max-requests-jitter="${ELIOT_GUNICORN_MAX_REQUESTS_JITTER}" \
    --access-logfile - \
    eliot.wsgi:application
