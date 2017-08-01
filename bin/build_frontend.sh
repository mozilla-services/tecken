#!/bin/bash
set -eo pipefail

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Builds the React frontend

pushd frontend
if [[ -z ${CI+check} ]]; then
    echo "NOT running in CI"
    yarn
    yarn run build
else
    echo "Running this in CI"
    yarn --no-progress --non-interactive
    yarn run --no-progress --non-interactive build
fi
mv build /app/frontend/
popd
