#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

# create a frontend/build/ directory if it doesn't exist
[ ! -d frontend/build/ ] && mkdir -p frontend/build/

# default variables
export DEVELOPMENT=1
export DJANGO_CONFIGURATION=Test

if [ "$1" = "--shell" ]; then
    bash
else
    # python manage.py collectstatic --noinput
    pytest
fi
