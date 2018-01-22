# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import os

import requests


BASE_URL = os.environ.get('BASE_URL')
assert BASE_URL


def test_basic_head_and_get():
    uri = '/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym'
    url = BASE_URL + uri
    head_response = requests.head(url)
    assert head_response.status_code in (200, 404)

    get_response = requests.get(url)
    assert get_response.status_code in (404, 302)
