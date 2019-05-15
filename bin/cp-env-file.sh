#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

FILEPATH="$(pwd)/.env"
DISTFILEPATH="$(pwd)/.env-dist"

if [ ! -f "${FILEPATH}" ]; then
    echo "# Copied $(git rev-parse --short HEAD | tr -d '\n') at $(date | tr -d '\n')" > "${FILEPATH}"
    echo "" >> "${FILEPATH}"
    cat < "${DISTFILEPATH}" >> "${FILEPATH}"
fi
