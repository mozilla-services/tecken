#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -e

# Usage: ./setup_tests.sh

STACKSDIR="./data/stacks/"
ZIPSDIR="./data/zip-files/"

echo "Generating systemtest data files ..."

# Generate some stacks for symbolication
mkdir -p "${STACKSDIR}" || true
STACKSCOUNT=$(find "${STACKSDIR}" -type f | wc -l)
if [ ${STACKSCOUNT} -lt 10 ]; then
    echo "NOTE: You'll want to double check the stacks files to make sure they're not "
    echo "silly looking."
    echo ""
    ./bin/fetch-crashids.py --num-results=10 | ./bin/make-stacks.py save "${STACKSDIR}"
else
    echo "Already have ${STACKSCOUNT} stacks files."
fi

# Generate some symbols ZIP files
mkdir -p "${ZIPSDIR}" || true
ZIPSCOUNT=$(find "${ZIPSDIR}" -type f | wc -l)
if [ ${ZIPSCOUNT} -lt 2 ]; then
    ./bin/make-symbols-zip.py --max-size=10000000 --start-page=1 --auth-token="${PROD_AUTH_TOKEN}" "${ZIPSDIR}"
    ./bin/make-symbols-zip.py --max-size=50000000 --start-page=10 --auth-token="${PROD_AUTH_TOKEN}" "${ZIPSDIR}"
else
    echo "Already have ${ZIPSCOUNT} zip files."
fi
