#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import itertools
import subprocess


def run():

    exceptions = (
        'docs/conf.py',
        'tests/blockade.py',
        'setup.py',
    )

    alreadies = subprocess.check_output([
        'git', 'grep',
        'This Source Code Form is subject to the terms of the Mozilla Public'
    ]).splitlines()
    alreadies = [x.split(':')[0] for x in alreadies]

    out = subprocess.check_output(['git', 'ls-files']).splitlines()

    suspect = []
    for fp in out:
        if fp in alreadies:
            continue
        if not os.stat(fp).st_size:
            continue
        if fp in exceptions:
            continue
        if True in itertools.imap(fp.endswith, ('.py', '.js')):
            suspect.append(fp)

    for i, fp in enumerate(suspect):
        if not i:
            print('The following appear to lack a license preamble:'.upper())
        print(fp)

    return len(suspect)


if __name__ == '__main__':
    import sys
    sys.exit(run())
