# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from tecken.base import utils

import pytest


@pytest.mark.parametrize(
    "debug_filename, filename",
    [
        (
            "xül.pdb",  # <-- note the extended ascii char
            "xul.sym",
        ),
        (
            "x%l.pdb",  # <-- note the %
            "xul.sym",
        ),
        (
            "xul.pdb",
            "xul#.ex_",  # <-- note the #
        ),
        (
            "crypt3\x10.pdb",
            "crypt3\x10.pd_",
        ),
    ],
)
def test_invalid_keys(debug_filename, filename):
    key = debug_filename + filename
    assert utils.invalid_key_name_characters(key) is True


@pytest.mark.parametrize(
    "debug_filename, filename",
    [
        (
            "xul.so",
            "xul.sym",
        ),
        (
            # bug 1954518: ~ is a valid character
            "libgallium-24.2.8-1~bpo12+rpt1.so",
            "libgallium-24.2.8-1~bpo12+rpt1.sym",
        ),
    ],
)
def test_valid_keys(debug_filename, filename):
    key = debug_filename + filename
    assert utils.invalid_key_name_characters(key) is False
