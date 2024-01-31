#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -e

# Usage: ./setup_tests.sh

ZIPSDIR="./data/zip-files/"

echo "Generating systemtest data files ..."

# Generate a CSV of symbols files to download
./bin/setup-download-tests.py --start-page=1 --auth-token="${PROD_AUTH_TOKEN}" "./data/sym_files_to_download.csv"


# Generate some symbols ZIP files to upload
mkdir -p "${ZIPSDIR}" || true
ZIPSCOUNT=$(find "${ZIPSDIR}" -type f | wc -l)
if [ ${ZIPSCOUNT} -lt 2 ]; then
    # TODO: Restore `--max-size` params of 10000000 and 50000000 before opening PR
    ./bin/make-symbols-zip.py --max-size=10000 --start-page=1 --auth-token="${PROD_AUTH_TOKEN}" "${ZIPSDIR}"
    ./bin/make-symbols-zip.py --max-size=10000 --start-page=10 --auth-token="${PROD_AUTH_TOKEN}" "${ZIPSDIR}"
else
    echo "Already have ${ZIPSCOUNT} zip files."
fi
