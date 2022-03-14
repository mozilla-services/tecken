#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

# create a frontend/build/ directory if it doesn't exist
[ ! -d frontend/build/ ] && mkdir -p frontend/build/

# default variables
export DEVELOPMENT=1

if [ "$1" = "--shell" ]
then
    bash
fi

TESTSUITE="${1:-}"

if [[ "$TESTSUITE" == "" ]] || [[ "$TESTSUITE" == "tecken" ]]
then
    # Run tecken tests
    pytest
fi

if [[ "$TESTSUITE" == "" ]] || [[ "$TESTSUITE" == "eliot" ]]
then
    # Run eliot-service tests
    pushd eliot-service
    pytest
    popd
fi
