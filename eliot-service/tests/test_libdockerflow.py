# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from eliot.libdockerflow import get_version_info, get_release_name


def test_get_version_info(tmpdir):
    fn = tmpdir.join("/version.json")
    fn.write_text(
        '{"commit": "d6ac5a5d2acf99751b91b2a3ca651d99af6b9db3"}', encoding="utf-8"
    )

    assert get_version_info(str(tmpdir)) == {
        "commit": "d6ac5a5d2acf99751b91b2a3ca651d99af6b9db3"
    }


def test_get_release_name(tmpdir):
    fn = tmpdir.join("/version.json")
    fn.write_text(
        '{"commit": "d6ac5a5d2acf99751b91b2a3ca651d99af6b9db3", "version": "44.0"}',
        encoding="utf-8",
    )
    assert get_release_name(str(tmpdir)) == "44.0:d6ac5a5d"


def test_get_release_name_no_commit(tmpdir):
    fn = tmpdir.join("/version.json")
    fn.write_text('{"version": "44.0"}', encoding="utf-8")
    assert get_release_name(str(tmpdir)) == "44.0:unknown"


def test_get_release_name_no_version(tmpdir):
    fn = tmpdir.join("/version.json")
    fn.write_text(
        '{"commit": "d6ac5a5d2acf99751b91b2a3ca651d99af6b9db3"}', encoding="utf-8"
    )
    assert get_release_name(str(tmpdir)) == "none:d6ac5a5d"


def test_get_release_name_no_file(tmpdir):
    assert get_release_name(str(tmpdir)) == "none:unknown"
