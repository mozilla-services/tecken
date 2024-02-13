#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os

from systemtests.bin.setup_download_tests import setup_download_tests
from systemtests.bin.setup_upload_tests import setup_upload_tests

# Usage: ./setup-tests.py
# This setup is only for non-prod envs (local and stage), as it uploads
# zip files to Tecken (destructive).

ZIPS_DIR = "./data/zip-files/"
PROD_AUTH_TOKEN = os.environ["PROD_AUTH_TOKEN"]

if not os.path.exists(ZIPS_DIR):
    # Create the zip output directory if it doesn't exist
    os.makedirs(ZIPS_DIR)

print("Generating systemtest data files ...")
try:
    zips_count = len(
        [
            name
            for name in os.listdir(f"{ZIPS_DIR}")
            if os.path.isfile(f"{ZIPS_DIR}/{name}")
        ]
    )
    if zips_count < 4:
        # Generate some symbols ZIP files to upload, and a CSV
        # of those symbols files to download
        setup_download_tests(
            [
                "--start-page",
                1,
                "--auth-token",
                f"{PROD_AUTH_TOKEN}",
                "./data/sym_files_to_download.csv",
                f"{ZIPS_DIR}",
            ],
            standalone_mode=False,
        )

        # Generate some symbols ZIP files to upload
        setup_upload_tests(
            [
                "--max-size",
                10000000,
                "--start-page",
                1,
                "--auth-token",
                f"{PROD_AUTH_TOKEN}",
                f"{ZIPS_DIR}",
            ],
            standalone_mode=False,
        )
        setup_upload_tests(
            [
                "--max-size",
                50000000,
                "--start-page",
                10,
                "--auth-token",
                f"{PROD_AUTH_TOKEN}",
                f"{ZIPS_DIR}",
            ],
            standalone_mode=False,
        )
    else:
        print(f"Already have ${zips_count} zip files.")
except Exception as exc:
    print(f"Unexpected error: {exc}")
