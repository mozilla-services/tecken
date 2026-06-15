# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from tecken.base import utils

import pytest


@pytest.mark.parametrize(
    "key",
    [
        "xül.pdb/1A2B3C4/xul.sym",  # <-- note the extended ascii char
        "x%l.pdb/1A2B3C4/xul.sym",  # <-- note the %
        "xul.pdb/1A2B3C/xul#.ex_",  # <-- note the #
        "xul.so/1A2B3G4E/xul.sym",  # <-- note the G in the debug id
        "crypt3\x10.pdb/1A2B3C/crypt3\x10.pd_",
    ],
)
def test_invalid_keys(key):
    assert not utils.validate_key(key)


@pytest.mark.parametrize(
    "key",
    [
        "xul.so/1A2B3C/xul.sym",
        # bug 1954518: ~ is a valid character
        "libgallium-24.2.8-1~bpo12+rpt1.so/1a2b3c/libgallium-24.2.8-1~bpo12+rpt1.sym",
    ],
)
def test_valid_keys(key):
    assert utils.validate_key(key)
