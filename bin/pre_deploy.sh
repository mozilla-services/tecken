#!/usr/bin/env bash
# Tasks run after the Heroku buildpack compile, but prior to the deploy.
# Failures will block the deploy unless `IGNORE_PREDEPLOY_ERRORS` is set.
if [[ -v SKIP_PREDEPLOY ]]; then
    echo "-----> PRE-DEPLOY: Warning: Skipping pre-deploy!"
    exit 0
fi

if [[ -v IGNORE_PREDEPLOY_ERRORS ]]; then
    echo "-----> PRE-DEPLOY: Warning: Ignoring errors during pre-deploy!"
else
    # Make non-zero exit codes & other errors fatal.
    set -euo pipefail
fi

echo "-----> PRE-DEPLOY: Running Django migration..."
./manage.py migrate --noinput

echo "-----> PRE-DEPLOY: Complete!"
