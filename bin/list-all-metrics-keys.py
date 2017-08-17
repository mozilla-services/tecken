#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
Script to print out the contents of the 'all-metrics-key.json' file.
Useful to get an insight into what metrics keys are being used.
"""

import json
import time


def run():
    with open('all-metrics-keys.json') as f:
        all_keys = json.load(f)
    for key in sorted(all_keys):
        if key.startswith('_documentation'):
            continue
        age = time.time() - all_keys[key]['timestamp']
        print(
            key.ljust(55),
            all_keys[key]['type'].ljust(10),
            '{} times'.format(all_keys[key]['count']).ljust(10),
            '' if age < 1000 else 'longtimeago'
        )


if __name__ == '__main__':
    import sys
    sys.exit(run())
