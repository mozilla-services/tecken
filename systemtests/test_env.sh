#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -e

# Runs through downloading, uploading, and symbolication tests.

# To use:
#
# 1. run "make shell" to get a shell in the container
# 2. then do "cd systemtests"
# 3. run "./test_env.sh [ENV]"

USAGE="Usage: test_env.sh [local|stage|prod]"

if [[ $# -eq 0 ]]; then
    echo "${USAGE}"
    exit 1;
fi

case $1 in
    "local")
        export DESTRUCTIVE_TESTS=1
        HOST=http://localhost:8000/
        export AUTH_TOKEN="${LOCAL_AUTH_TOKEN}"
        ;;
    "stage")
        export DESTRUCTIVE_TESTS=1
        HOST=https://symbols.stage.mozaws.net/
        export AUTH_TOKEN="${STAGE_AUTH_TOKEN}"
        ;;
    "prod")
        echo "Running tests in prod--skipping destructive tests!"
        HOST=https://symbols.mozilla.org/
        export AUTH_TOKEN="${PROD_AUTH_TOKEN}"
        ;;
    *)
        echo "${USAGE}"
        exit 1;
        ;;
esac

echo "HOST: ${HOST}"
echo ""

# Test symbolication API
echo ">>> SYMBOLICATION TEST"
for FN in ./data/stacks/*.json
do
    # Verify v4 api
    python ./bin/symbolicate.py --verify --api-url="${HOST}symbolicate/v4" --api-version=4 "${FN}"
    # Verify v5 api
    python ./bin/symbolicate.py --verify --api-url="${HOST}symbolicate/v5" --api-version=5 "${FN}"
done

# FIXME: finish this off
exit 1;

# Test uploading -- requires AUTH_TOKEN in environment
# FIXME: if upload-zips doesn't exist, create it here
# mkdir upload-zips
# python bin/make-symbol-zip.py --save-dir upload-zips
echo ">>> UPLOAD TEST"
python systemtests/bin/upload-symbol-zips.py --timeout=600 ${HOST}
echo ""

# Test upload by download url
echo ">>> UPLOAD BY DOWNLOAD TEST"
URL=$(python bin/list-firefox-symbols-zips.py --url-only --number=1)
python systemtests/bin/upload-symbol-zips.py --timeout=600 --download-url=${URL} --max-size=1500mb ${HOST}
echo ""

# Test downloading
echo ">>> DOWNLOAD TEST"
python systemtests/bin/download.py --max-requests=50 ${HOST} downloading/symbol-queries-groups.csv
echo ""

