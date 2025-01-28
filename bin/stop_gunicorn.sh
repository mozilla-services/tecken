#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Send the TERM signal to gunicorn to trigger a graceful shutdown, and wait for
# it to exit.

set -euo pipefail

# Wait 30 seconds for HAProxy to remove the pod from its backend list.
sleep 30

pid=$(cat /tmp/gunicorn.pid)

if [ -n "$pid" ]; then
    echo "Sending TERM signal to gunicorn."
    kill -TERM "$pid"
    echo "Waiting for gunicorn to exit..."
    while kill -0 "$pid" 2>/dev/null; do
        sleep 1
    done
fi
