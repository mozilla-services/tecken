#!/bin/bash
set -eo pipefail

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Builds the React frontend.

# NOTE(willkg): Since this is in the image at /app/frontend/build, it gets
# stomped on when you mount your repo directory as /app.

# Because this is what create-react-app needs as a prefix
export REACT_APP_SENTRY_PUBLIC_DSN=$FRONTEND_SENTRY_PUBLIC_DSN

# We prefer to not leave any JavaScript as inline no matter how small.
export INLINE_RUNTIME_CHUNK=false

pushd frontend
yarn --no-progress
yarn run --no-progress build
popd
