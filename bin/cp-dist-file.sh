#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copies a dist file and replaces $Id$ with the git sha and date copied.

if [[ $# -lt 2 ]]; then
    echo "Usage: bin/cp-dist-file.sh DISTFILEPATH FILEPATH"
    exit 1
fi

DISTFILEPATH=$1
FILEPATH=$2

if [ ! -f "${FILEPATH}" ]; then
    SOURCELINE="Copied $(git rev-parse --short HEAD | tr -d '\n') at $(date | tr -d '\n')"
    sed "s/\\\$Id\\\$/${SOURCELINE}/" < "${DISTFILEPATH}" > "${FILEPATH}"
fi
