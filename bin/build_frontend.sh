#!/bin/bash
set -eo pipefail

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Builds the React frontend

pushd frontend
yarn --no-progress
yarn run --no-progress build
popd
