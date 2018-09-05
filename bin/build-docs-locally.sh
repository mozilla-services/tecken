#!/bin/bash

python3 -m venv ./docsvenv
source docsvenv/bin/activate
pip install -r docs-requirements.txt
cd docs
source ../docsvenv/bin/activate
make html

echo ""
echo "Now open:"
echo ""
echo "    file://`pwd -P`/_build/html/index.html"
echo ""
