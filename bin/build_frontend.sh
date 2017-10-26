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
fi
