# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from unittest import mock


class TestHealthChecks:
    def test_no_version(self, client, tmpdir):
        with mock.patch("eliot.app.REPOROOT_DIR", new=str(tmpdir)):
            client.rebuild_app()

            result = client.simulate_get("/__version__")
            assert result.content == b"{}"

    def test_version(self, client, tmpdir):
        version_path = tmpdir.join("/version.json")
        version_path.write('{"commit": "ou812"}')

        with mock.patch("eliot.app.REPOROOT_DIR", new=str(tmpdir)):
            client.rebuild_app()

            result = client.simulate_get("/__version__")
            assert result.content == b'{"commit": "ou812"}'

    def test_lb_heartbeat(self, client):
        resp = client.simulate_get("/__lbheartbeat__")
        assert resp.status_code == 200

    def test_heartbeat(self, client):
        resp = client.simulate_get("/__heartbeat__")
        assert resp.status_code == 200

    def test_broken(self, client):
        resp = client.simulate_get("/__broken__")
        assert resp.status_code == 500
