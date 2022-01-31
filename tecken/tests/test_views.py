# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import json
from pathlib import Path

import pytest

from django.core.exceptions import PermissionDenied
from django.urls import reverse

from tecken.views import handler500, handler400, handler403


def test_dashboard(client, db, settings, tmpdir):
    settings.FRONTEND_ROOT = str(tmpdir)
    f = Path(tmpdir / "index.html")
    f.write_bytes(b"<html><h1>Hi!</h1></html>")

    response = client.get("/")
    assert response.status_code == 200
    assert response["content-type"] == "text/html"
    html = response.getvalue()
    assert b"<h1>Hi!</h1>" in html

    # .close() to avoid ResourceWarning for unclosed file object.
    response.close()


def test_frontend_index_html_redirect(client, db, settings, tmpdir):
    # If you hit this URL with '/index.html' explicit it redirects.
    # But only if there is no 'index.html' file in settings.FRONTEND_ROOT.
    settings.FRONTEND_ROOT = str(tmpdir)
    response = client.get("/index.html")
    assert response.status_code == 302
    assert response["location"] == "/"

    # .close() to avoid ResourceWarning for unclosed file object.
    response.close()


def test_frontend_index_html_aliases(client, db, settings, tmpdir):
    settings.FRONTEND_ROOT = str(tmpdir)
    f = Path(tmpdir / "index.html")
    f.write_bytes(b"<html><h1>React Routing!</h1></html>")

    # For example `/help` is a route taking care of in the React app.
    response = client.get("/help")
    assert response.status_code == 200
    assert response["content-type"] == "text/html"

    # .close() to avoid ResourceWarning for unclosed file object.
    response.close()

    # Should work if there's a second path too
    response = client.get("/help/deeper/page")
    assert response.status_code == 200
    assert response["content-type"] == "text/html"

    # .close() to avoid ResourceWarning for unclosed file object.
    response.close()

    response = client.get("/neverheardof")
    assert response.status_code == 404

    # .close() to avoid ResourceWarning for unclosed file object.
    response.close()


def test_contribute_json(client, db):
    url = reverse("contribute_json")
    response = client.get(url)
    assert response.status_code == 200
    # No point testing that the content can be deserialized because
    # the view would Internal Server Error if the ./contribute.json
    # file on disk is invalid.
    assert response["Content-type"] == "application/json"

    # .close() to avoid ResourceWarning for unclosed file object.
    response.close()


def test_handler500(rf):
    request = rf.get("/")
    response = handler500(request)
    assert response.status_code == 500
    assert response["Content-type"] == "application/json"
    assert json.loads(response.content.decode("utf-8"))["error"]


def test_handler400(rf):
    request = rf.get("/")
    response = handler400(request, NameError("foo is bar"))

    assert response.status_code == 400
    assert response["Content-type"] == "application/json"
    assert json.loads(response.content.decode("utf-8"))["error"] == "foo is bar"


def test_handler403(rf):
    request = rf.get("/")
    response = handler403(request, PermissionDenied("bad boy!"))
    assert response.status_code == 403
    assert response["Content-type"] == "application/json"
    assert json.loads(response.content.decode("utf-8"))["error"] == "bad boy!"


def test_handler404(client):
    # This handler is best tested as an integration test because
    # it's a lot easier to simulate.
    response = client.get("/blabla")
    assert response.status_code == 404
    assert response["Content-type"] == "application/json"
    information = json.loads(response.content.decode("utf-8"))
    assert information["error"]
    assert information["path"] == "/blabla"


@pytest.mark.django_db
def test_auth_debug(client):
    url = reverse("auth_debug")

    response = client.get(url)
    assert response.status_code == 200
    text = response.content.decode("utf-8")
    assert "Refresh to see if caching works." in text
    assert "Refresh to see if session cookies work." in text

    response = client.get(url)
    assert response.status_code == 200
    text = response.content.decode("utf-8")
    assert "Cache works!" in text
    assert "Session cookies work!" in text


@pytest.mark.django_db
def test_heartbeat_no_warnings(client, botomock):
    def mock_api_call(self, operation_name, api_params):
        assert operation_name == "HeadBucket"
        return {}

    with botomock(mock_api_call):
        response = client.get("/__heartbeat__")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_broken(client):
    with pytest.raises(Exception):
        client.get(reverse("broken"))
