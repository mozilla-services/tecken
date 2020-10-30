#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# default variables
: "${ELIOT_PORT:=8000}"
: "${ELIOT_GUNICORN_WORKERS:=1}"
: "${ELIOT_GUNICORN_TIMEOUT:=300}"

(set -o posix; set) | grep ELIOT

cd /app/eliot-service/

${CMD_PREFIX} gunicorn \
    --bind 0.0.0.0:"${ELIOT_PORT}" \
    --timeout "${ELIOT_GUNICORN_TIMEOUT}" \
    --workers "${ELIOT_GUNICORN_WORKERS}" \
    --preload \
    --access-logfile - \
    eliot.wsgi:application
