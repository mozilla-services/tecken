#!/bin/bash

# Send the TERM signal to gunicorn to trigger a graceful shutdown, and wait for it to exit.

set -euo pipefail

pid=`cat /tmp/gunicorn.pid`

if [ -n "$pid" ]; then
    echo "Sending TERM signal to gunicorn."
    kill -TERM "$pid"
    echo "Waiting for gunicorn to exit..."
    while kill -0 $pid 2>/dev/null; do
        sleep 1
    done
fi
