#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Usage: bin/run_web_disk_manager.sh
#
# Note: This should be called from inside a container.

set -euo pipefail

cd /app/

export PROCESS_NAME=disk_manager

# Run disk manager in a loop so that if it dies (ignore exit value), the loop
# pauses for 1 minute and then starts up again. This expects the disk manager
# to send errors to Sentry. The 1 minute sleep is to reduce the likelihood
# there's a spike in error reports. The loop allows this to maybe recover
# depending on what the error was.
while true
do
    python manage.py remove_orphaned_files --daemon

    echo "Sleep 1 minute..."
    sleep 60
done

