#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

# Set up GCS
gcs-cli delete "${UPLOAD_GCS_BUCKET}"
gcs-cli create "${UPLOAD_GCS_BUCKET}"

# Set up db
python bin/db.py drop || true
python bin/db.py create
python manage.py migrate --noinput
