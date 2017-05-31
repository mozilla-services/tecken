# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from django.contrib.auth.models import User

from tecken.views import server_error


def test_server_error(rf):
    request = rf.get('/')
    response = server_error(request)
    assert response.status_code == 500

    response = server_error(request, template_name='non-existing.html')
    assert response.status_code == 500


@pytest.mark.django_db
def test_dashboard(client):
    response = client.get('/')
    assert response.status_code == 200
    information = response.json()
    assert 'documentation' in information
    assert 'sign_in_url' in information['user']

    # Now pretend the user goes through the OIDC steps to sign in
    user = User.objects.create(username='peterbe', email='peterbe@example.com')
    user.set_password('secret')
    user.save()
    assert client.login(username='peterbe', password='secret')

    response = client.get('/')
    assert response.status_code == 200
    information = response.json()
    assert 'documentation' in information
    assert 'sign_in_url' not in information['user']
    assert 'sign_out_url' in information['user']
    assert information['user']['email'] == 'peterbe@example.com'
    assert information['user']['active']
