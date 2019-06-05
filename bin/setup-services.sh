#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

# Drops and recreates Postgres db and Elasticsearch indexes.

# Set up db
python bin/db.py drop || true
python bin/db.py create
python manage.py migrate --noinput
