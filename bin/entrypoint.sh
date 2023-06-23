#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Entrypoint script for the tecken docker image.
#
# Usage: entrypoint.sh SERVICE
#
# web: runs the webapp
#
# bash: if no additional arguments, runs the bash shell; if additional
# arguments, runs that.

set -eo pipefail

if [ -z "$*" ]; then
    echo "usage: entrypoint.sh SERVICE"
    echo ""
    echo "Services:"
    grep -E '^[a-zA-Z0-9_-]+).*?## .*$$' /app/bin/entrypoint.sh \
        | grep -v grep \
        | sed -n 's/^\(.*\)) \(.*\)##\(.*\)/* \1:\3/p'
    exit 1
fi

# Only wait for backend services in local development and CI
if [ ! -z ${DEVELOPMENT+check} ]; then
    echo "Waiting for services..."
    urlwait postgres://db:5432 10
    urlwait redis://redis-cache:6379 10
fi

SERVICE=$1
shift

case ${SERVICE} in
web)  ## Run Tecken web service
    exec honcho -f /app//Procfile --no-prefix start
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
