#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

if [ -z "$*" ]; then
    echo "usage: entrypoint.sh SERVICE"
    echo ""
    echo "Services:"
    grep -E '^[a-zA-Z0-9_-]+).*?## .*$$' bin/entrypoint.sh \
        | grep -v grep \
        | sed -n 's/^\(.*\)) \(.*\)##\(.*\)/* \1:\3/p'
    exit 1
fi

# Only wait for backend services in local development and CI
if [ ! -z ${DEVELOPMENT+check} ]; then
    echo "Waiting for services..."
    urlwait postgres://db:5432 10
    urlwait redis://redis-cache:6379 10
    urlwait redis://redis-store:6379 10
fi

SERVICE=$1
shift

case ${SERVICE} in
web)  ## Run Tecken web service
    exec ./bin/run_web.sh $@
    ;;
worker)  ## Run Celery worker
    exec ${CMD_PREFIX} celery -A tecken.celery:app worker --loglevel INFO
    ;;
worker-purge)  ## Purge Celery tasks
    # Start worker but first purge ALL old stale tasks.
    # Only useful in local development where you might have accidentally
    # started waaaay too make background tasks when debugging something.
    # Or perhaps the jobs belong to the wrong branch as you stop/checkout/start
    # the docker container.
    exec celery -A tecken.celery:app worker --loglevel INFO --purge
    ;;
bash)  ## Open a bash shell or run something else
    if [ -z "$*" ]; then
        bash
    else
        "$@"
    fi
    ;;
*)
    echo "Unknown service ${SERVICE}"
    exit 1
esac
