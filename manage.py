#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tecken.settings')
    os.environ.setdefault('DJANGO_CONFIGURATION', 'Localdev')

    from configurations.management import execute_from_command_line

    execute_from_command_line(sys.argv)
