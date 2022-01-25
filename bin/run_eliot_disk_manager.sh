#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -euo pipefail

cd /app/eliot-service/

# Run cache manager in a loop so that if it dies (ignore exit value), the loop
# pauses for 1 minute and then starts up again. This expects disk cache manager
# to send errors to Sentry. The 1 minute sleep is to reduce the likelihood
# there's a spike in error reports. The loop allows this to maybe recover
# depending on what the error was.
while true
do
    PYTHONPATH=.:$PYTHONPATH python eliot/cache_manager.py || true

    echo "Sleep 1 minute..."
    sleep 60
done
