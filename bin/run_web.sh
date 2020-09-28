#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# default variables
: "${PORT:=8000}"
: "${GUNICORN_WORKERS:=4}"
: "${GUNICORN_TIMEOUT:=300}"

if [ "$1" == "--dev" ]; then
    python manage.py migrate --noinput
    python manage.py runserver 0.0.0.0:${PORT}

else
    echo "GUNICORN_WORKERS=${GUNICORN_WORKERS}"
    echo "GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT}"
    echo "PORT=${PORT}"
    ${CMD_PREFIX} gunicorn \
        --bind 0.0.0.0:"${PORT}" \
        --timeout "${GUNICORN_TIMEOUT}" \
        --workers "${GUNICORN_WORKERS}" \
        --access-logfile - \
        tecken.wsgi:application
fi
