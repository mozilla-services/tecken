#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Usage: bin/run_lint.sh [--fix]
#
# Runs linting and code fixing.
#
# This should be called from inside a container.

set -e

BLACKARGS=("--line-length=88" "--target-version=py36" bin tecken eliot-service systemtests)

if [[ $1 == "--fix" ]]; then
    echo ">>> black fix"
    black "${BLACKARGS[@]}"

else
    echo ">>> flake8 ($(python --version))"
    cd /app
    flake8

    echo ">>> black"
    black --check "${BLACKARGS[@]}"

    echo ">>> license check"
    python bin/license_check.py
fi
