#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

# copy the .env template to .env if not there already
[ ! -f .env ] && cp .env-dist .env

# create a frontend/build/ directory if it doesn't exist
[ ! -d frontend/build/ ] && mkdir -p frontend/build/

# start services--this gives them a little time to start up before we
# start the test container
docker-compose up -d db redis-store redis-cache minio statsd oidcprovider

# default variables
export DEVELOPMENT=1
export DJANGO_CONFIGURATION=Test

# run docker compose with the correct given environment variables
if [[ -n "${CI}" ]]; then
    docker-compose run -e DEVELOPMENT -e DJANGO_CONFIGURATION test-ci test $@
else
    docker-compose run -e DEVELOPMENT -e DJANGO_CONFIGURATION test test $@
fi
