#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# This builds a new yarn.lock file and deals with vestigal node_modules/
# directory.
#
# Run this from the frontend container.
#
# Usage: ./bin/build_yarn_lock.sh

set -e

rm -rf node_modules
rm yarn.lock
yarn install | cat
rm -rf node_modules

echo "Run 'make build' now."
