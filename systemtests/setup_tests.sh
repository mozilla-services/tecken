#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -e

# Usage: ./setup_tests.sh
# This setup is only for non-prod envs (local and stage), as it uploads
# zip files to Tecken (destructive).

ZIPSDIR="./data/zip-files/"

echo "Generating systemtest data files ..."

mkdir -p "${ZIPSDIR}" || true
ZIPSCOUNT=$(find "${ZIPSDIR}" -type f | wc -l)
if [ ${ZIPSCOUNT} -lt 4 ]; then
    # Generate some symbols ZIP files to upload, and a CSV
    # of those symbols files to download
    ./bin/setup-download-tests.py --start-page=1 --auth-token="${PROD_AUTH_TOKEN}" "./data/sym_files_to_download.csv" "${ZIPSDIR}"

    # # Generate some symbols ZIP files to upload
    ./bin/setup-upload-tests.py --max-size=10000000 --start-page=1 --auth-token="${PROD_AUTH_TOKEN}" "${ZIPSDIR}"
    ./bin/setup-upload-tests.py --max-size=50000000 --start-page=10 --auth-token="${PROD_AUTH_TOKEN}" "${ZIPSDIR}"
else
    echo "Already have ${ZIPSCOUNT} zip files."
fi
