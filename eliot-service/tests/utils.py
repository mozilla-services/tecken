# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


def counter():
    """Yields "better" ids for parametrized test cases"""
    count = 0
    while True:
        yield "case-%s" % count
        count += 1
