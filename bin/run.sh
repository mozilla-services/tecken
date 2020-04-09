#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

# default variables
: "${PORT:=8000}"
: "${SLEEP:=1}"
: "${TRIES:=60}"
: "${GUNICORN_WORKERS:=4}"
: "${GUNICORN_TIMEOUT:=300}"

usage() {
  echo "usage: ./bin/run.sh web|web-dev|worker|test|bash|lint|lintfix|superuser"
  exit 1
}

wait_for() {
  tries=0
  echo "Waiting for $1 to listen on $2..."
  while true; do
    [[ $tries -lt $TRIES ]] || return
    (echo > /dev/tcp/$1/$2) >/dev/null 2>&1
    result=
    [[ $? -eq 0 ]] && return
    sleep $SLEEP
    tries=$((tries + 1))
  done
}

[ $# -lt 1 ] && usage

# Only wait for backend services in development
# http://stackoverflow.com/a/13864829
# For example, bin/test.sh sets 'DEVELOPMENT' to something
[ ! -z ${DEVELOPMENT+check} ] && wait_for db 5432 && wait_for redis-cache 6379 && wait_for redis-store 6379

case $1 in
  web)
    ${CMD_PREFIX} gunicorn tecken.wsgi:application -b 0.0.0.0:${PORT} --timeout ${GUNICORN_TIMEOUT} --workers ${GUNICORN_WORKERS} --access-logfile -
    ;;
  web-dev)
    python manage.py migrate --noinput
    exec python manage.py runserver 0.0.0.0:${PORT}
    ;;
  worker)
    exec ${CMD_PREFIX} celery -A tecken.celery:app worker -l info
    ;;
  worker-purge)
    # Start worker but first purge ALL old stale tasks.
    # Only useful in local development where you might have accidentally
    # started waaaay too make background tasks when debugging something.
    # Or perhaps the jobs belong to the wrong branch as you stop/checkout/start
    # the docker container.
    exec celery -A tecken.celery:app worker -l info --purge
    ;;
  lintfix)
    # This exclude is ugly because it's not additive
    # See https://github.com/ambv/black/issues/65
    black tecken tests systemtests --exclude '/(\.git|\.hg|\.mypy_cache|\.tox|\.venv|_build|buck-out|build|dist|migrations)/'
    ;;
  lint)
    flake8 tecken tests
    black --diff --check tecken tests systemtests --exclude '/(\.git|\.hg|\.mypy_cache|\.tox|\.venv|_build|buck-out|build|dist|migrations)/'
    ;;
  superuser)
    exec python manage.py superuser "${@:2}"
    ;;
  test)
    if [ "$2" = "--shell" ]; then
      bash
    else
      # python manage.py collectstatic --noinput
      coverage erase
      coverage run -m pytest "${@:2}"
      coverage report -m
    fi
    ;;
  bash)
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
