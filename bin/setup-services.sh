#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

# Set up S3
python bin/s3.py delete "http://minio:9000/testbucket"
python bin/s3.py create "http://minio:9000/testbucket"

# Set up db
python bin/db.py drop || true
python bin/db.py create
python manage.py migrate --noinput
