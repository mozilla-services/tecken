# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


class Test404:
    def test_404(self, client):
        result = client.simulate_get("/foo")
        assert result.status_code == 404
        assert result.headers["Content-Type"].startswith("application/json")
