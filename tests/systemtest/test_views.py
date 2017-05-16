# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os
import requests

BASE_URL = os.environ.get('BASE_URL')
assert BASE_URL


def test_task_tester():
    url = BASE_URL + '/__task_tester__'
    response = requests.post(url)
    assert response.status_code == 201
    response = requests.get(url)
    assert response.status_code == 200
    assert b'It works!' in response.content
