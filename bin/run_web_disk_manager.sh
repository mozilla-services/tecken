#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Usage: bin/run_web_disk_manager.sh
#
# Note: This should be called from inside a container.

# NOTE(willkg): we don't want errors to kill the script, so we don't have set
# -e enabled.
set -uo pipefail

cd /app/

export PROCESS_NAME=disk_manager

SLEEP_SECONDS=60
PROCESS_TIMEOUT_SECONDS=120

# Run disk manager in a loop sleeping SLEEP_SECONDS between rounds. Wrap in
# sentry-wrap so it sends errors to Sentry.
while true
do
    python /app/bin/sentry-wrap.py wrap-process --timeout="${PROCESS_TIMEOUT_SECONDS}" -- \
        python /app/manage.py remove_orphaned_files --skip-checks
    sleep "${SLEEP_SECONDS}"
done
