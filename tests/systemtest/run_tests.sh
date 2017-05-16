#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# This runs the system tests. It expects the following things to exist:
#
# * "python3" available in PATH
# * "virtualenv" available in PATH
#
# To run this from the root of this repository, do this:
#
#     $ ./tests/systemtests/run_tests.sh
#
# Set BASE_URL to the URL to base things one.
#

set -ex

cd /app

VENV_DIR=/tmp/tecken-systemtests-venv/
if [ -z "${BASE_URL}" ]; then
    # This is the posturl when running against a local dev environment
    export BASE_URL="http://web:8000/"
fi
echo "BASE_URL: ${BASE_URL}"

cmd_required() {
    command -v "$1" > /dev/null 2>&1 || { echo >&2 "$1 required, but not on PATH. Exiting."; exit 1; }
}

echo "Setting up system tests."

# Verify python3 and virtualenv exist
cmd_required python3
echo "Required commands available."

# If venv exists, exit
if [ -d "${VENV_DIR}" ]; then
    echo "${VENV_DIR} exists. Please remove it and try again. Exiting."
    exit 1
fi

# Create virtualenv
python3 -m venv "${VENV_DIR}"

# Activate virtualenv
source "${VENV_DIR}/bin/activate"

# Install requirements into virtualenv
pip install --no-cache-dir -r tests/systemtest/requirements.txt

echo "Running tests."
# Run tests--this  uses configuration in the environment--and send everything to
# stdout
py.test -vv tests/systemtest/ "${@:1}" 2>&1
