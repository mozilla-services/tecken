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
#
# To set auth tokens, add these to your .env file:
#
# * LOCAL_AUTH_TOKEN
# * STAGE_AUTH_TOKEN
# * PROD_AUTH_TOKEN

USAGE="Usage: test_env.sh [local|stage|prod]"

if [[ $# -eq 0 ]]; then
    echo "${USAGE}"
    exit 1;
fi

case $1 in
    "local")
        export DESTRUCTIVE_TESTS=1
        export BAD_TOKEN_TEST=1
        HOST=http://web:8000/
        export AUTH_TOKEN="${LOCAL_AUTH_TOKEN}"
        ;;
    "stage")
        export DESTRUCTIVE_TESTS=1
        export BAD_TOKEN_TEST=1
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

# DESTRUCTIVE TESTS
if [ "${DESTRUCTIVE_TESTS}" == "1" ]; then
    echo ">>> UPLOAD TEST (DESTRUCTIVE)"
    for FN in ./data/zip-files/*.zip
    do
        python ./bin/upload-symbols.py --expect-code=201 --auth-token="${AUTH_TOKEN}" --base-url="${HOST}" "${FN}"
    done
    echo ""

    echo ">>> UPLOAD BY DOWNLOAD TEST (DESTRUCTIVE)"
    URL=$(python bin/list-firefox-symbols-zips.py --number=1 --max-size=1000000000)
    python ./bin/upload-symbols-by-download.py --base-url="${HOST}" --auth-token="${AUTH_TOKEN}" "${URL}"
    echo ""
else
    echo ">>> SKIPPING DESTRUCTIVE TESTS"
    echo ""
fi

if [ "${BAD_TOKEN_TEST}" == "1" ]; then
    # This tests a situation that occurs when nginx is a reverse-proxy to
    # tecken and doesn't work in the local dev environment. bug 1655944
    echo ">>> UPLOAD WITH BAD TOKEN TEST--this should return a 403 and error and not a RemoteDisconnected"
    FN=$(ls -S ./data/zip-files/*.zip | head -n 1)
    ls -l ${FN}
    python ./bin/upload-symbols.py --expect-code=403 --auth-token="badtoken" --base-url="${HOST}" "${FN}"
fi

echo ">>> SYMBOLICATION V4 and V5 TEST"
for FN in ./data/stacks/*.json
do
    # Verify v4 api
    python ./bin/symbolicate.py verify --api-url="${HOST}symbolicate/v4" --api-version=4 "${FN}"
    # Verify v5 api
    python ./bin/symbolicate.py verify --api-url="${HOST}symbolicate/v5" --api-version=5 "${FN}"
done

echo ""

echo ">>> DOWNLOAD TEST"
python ./bin/download-sym-files.py --base-url="${HOST}" ./data/sym_files_to_download.csv
echo ""

echo ">>> DOWNLOAD MISSING SYMBOLS CSV TEST"
python ./bin/download-missing-symbols.py --base-url="${HOST}"
