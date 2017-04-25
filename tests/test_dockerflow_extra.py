# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from tecken.dockerflow_extra import check_redis_store_connected


def test_check_redis_store_connected_happy_path():
    assert not check_redis_store_connected(None)
