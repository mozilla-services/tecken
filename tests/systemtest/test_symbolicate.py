# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import requests

BASE_URL = os.environ.get('BASE_URL')
assert BASE_URL


def _request(payload, uri='/symbolicate/v4', **options):
    url = BASE_URL + uri
    return requests.post(url, json=payload, timeout=30, **options)


def test_basic_symbolication_v4():
    crash_ping = {
        'version': 4,
        'memoryMap': [
            ['firefox.pdb', 'C617B8AF472444AD952D19A0CFD7C8F72'],
            ['wntdll.pdb', 'D74F79EB1F8D4A45ABCD2F476CCABACC2']
        ],
        'stacks': [
            [
                [0, 154348],
                [1, 65802]
            ]
        ]
    }
    response = _request(crash_ping)
    assert response.status_code == 200

    # Note that we deliberately don't look at the output values.
    # That's because the symbols content changes
    assert response.json()['symbolicatedStacks']
    assert response.json()['knownModules']
