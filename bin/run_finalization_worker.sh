#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Usage: bin/run_finalization_worker.sh
#
# Note: This should be called from inside a container.

set -euo pipefail

cd /app/

export PROCESS_NAME=finalization_worker

exec python /app/manage.py finalization_worker --skip-checks
