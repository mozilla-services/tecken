#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import print_function

import sys
import os


HERE = os.path.dirname(__file__)
TEMPLATE_FP = os.path.join(HERE, 'tecken-https.conf.template')


def run(hostname, destination):
    with open(TEMPLATE_FP) as f:
        config = f.read()
    config = config.replace('%HOSTNAME%', hostname)
    here = os.path.abspath(HERE)
    config = config.replace('%HERE%', here)
    config = config.replace('%ROOT%', os.path.abspath(os.path.join(
        here,
        '..',
    )))
    if destination:
        with open(destination, 'w') as f:
            print(config, file=f)
    else:
        print(config)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-o',
        '--output-file',
        help='Where to put this file (or else, stdout)',
        default='',
    )
    parser.add_argument(
        '--hostname',
        help='Hostname you prefer (default is prod.tecken.dev)',
        default='prod.tecken.dev',
    )
    args = parser.parse_args()
    return run(
        args.hostname,
        args.output_file,
    )


if __name__ == '__main__':
    sys.exit(main())
