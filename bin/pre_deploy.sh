#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Tasks run after the Heroku buildpack compile, but prior to the deploy.
# Failures will block the deploy unless `IGNORE_PREDEPLOY_ERRORS` is set.
if [[ -v SKIP_PREDEPLOY ]]; then
    echo "-----> PRE-DEPLOY: Warning: Skipping pre-deploy!"
    exit 0
fi

if [[ -v IGNORE_PREDEPLOY_ERRORS ]]; then
    echo "-----> PRE-DEPLOY: Warning: Ignoring errors during pre-deploy!"
else
    # Make non-zero exit codes & other errors fatal.
    set -euo pipefail
fi

echo "-----> PRE-DEPLOY: Running Django migration..."
./manage.py migrate --noinput

echo "-----> PRE-DEPLOY: Complete!"
