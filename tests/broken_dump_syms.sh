#!/bin/bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

# This script is used by the unittest to mock how it'd cope if
# dump_syms was to fail. I.e. no output on stdout but something on stderr.

>&2 echo "Something horrible happened"
exit 419
