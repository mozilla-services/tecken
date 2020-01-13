#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

python3 -m venv ./docsvenv
source docsvenv/bin/activate
pip install -r requirements/docs.txt
cd docs
source ../docsvenv/bin/activate
make html

echo ""
echo "Now open:"
echo ""
echo "    file://`pwd -P`/_build/html/index.html"
echo ""
