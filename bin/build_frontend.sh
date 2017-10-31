#!/bin/bash
set -eo pipefail

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Builds the React frontend, *only* if we are in CI.

# True if the environment variable 'CI' is NOT empty.
# In CircleCI, this variable is "true" and in local dev, it's "".
if [[ ! -z "${CI}" ]]; then
    # Because this is what create-react-app needs as a prefix
    export REACT_APP_SENTRY_PUBLIC_DSN=$FRONTEND_SENTRY_PUBLIC_DSN

    pushd frontend
    yarn --no-progress
    yarn run --no-progress build
    popd
else
    # If you're NOT in CI, you're most likely in a local development mode.
    # You need the Dockerfile to build as normal but you don't want to
    # build the production grade static assets necessarily (it's slow
    # and for local development you have the 'frontend' container in
    # docker-compose.yml).
    # This just makes sure there exists a directory called 'frontend/build'.
    # If it's empty, that's OK. It it already existed, it won't be
    # affected.
    mkdir -p frontend/build
fi
