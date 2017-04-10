#!/bin/bash
set -eo pipefail

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Builds docs in the docs/ directory.

# Install the Sphinx dependencies
pip install -r docs-requirements.txt

# Clean the docs first
make -C docs/ clean
mkdir -p docs/_build/
chmod -R 777 docs/_build/

# Build the HTML docs
make -C docs/ html

# Fix permissions
find docs/_build/ -type d -exec 'chmod' '777' '{}' ';'
find docs/_build/ -type f -exec 'chmod' '666' '{}' ';'
