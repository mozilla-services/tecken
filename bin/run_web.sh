#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Default variables
: "${PORT:=8000}"
: "${GUNICORN_WORKERS:=4}"
: "${GUNICORN_TIMEOUT:=600}"
: "${GUNICORN_GRACEFUL_TIMEOUT:=600}"

export PROCESS_NAME=webapp

if [ "$LOCAL_DEV_ENV" == "true" ]; then
    python manage.py migrate --noinput
    python manage.py runserver 0.0.0.0:${PORT}

else
    echo "GUNICORN_WORKERS=${GUNICORN_WORKERS}"
    echo "GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT}"
    echo "PORT=${PORT}"
    ${CMD_PREFIX} gunicorn \
        --pid /tmp/gunicorn.pid \
        --bind 0.0.0.0:"${PORT}" \
        --timeout "${GUNICORN_TIMEOUT}" \
        --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT}" \
        --workers "${GUNICORN_WORKERS}" \
        --config=tecken/gunicornhooks.py \
        --access-logfile - \
        tecken.wsgi:application
fi
