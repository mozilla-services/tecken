#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

# Set up S3
python bin/s3_cli.py delete "${UPLOAD_DEFAULT_URL}"
python bin/s3_cli.py create "${UPLOAD_DEFAULT_URL}"

# Set up GCS
# FIXME bug 1827506: update argument as needed once GCS is
# implemented in the source code.
python bin/gcs_cli.py delete publicbucket
python bin/gcs_cli.py create publicbucket

# Set up db
python bin/db.py drop || true
python bin/db.py create
python manage.py migrate --noinput
