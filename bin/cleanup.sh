#!/bin/bash
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Usage: bin/cleanup.sh
#
# Runs Django commands to clean up application state.

set -eo pipefail

# Remove stale contenttypes
echo ">>> running remove_stale_contenttypes"
time python manage.py remove_stale_contenttypes

# Clear expired sessions
echo ""
echo ">>> running clearsessions"
time python manage.py clearsessions

# Clear expired upload and fileupload records
echo ""
echo ">>> running clearuploads"
time python manage.py clearuploads
