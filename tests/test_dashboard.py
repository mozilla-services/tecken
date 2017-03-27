# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

# import pytest
# from django.core.urlresolvers import reverse
# from django.utils import timezone

# from atmo.clusters.models import Cluster
# from atmo.jobs.models import SparkJob
from tecken.views import server_error


def test_server_error(rf):
    request = rf.get('/')
    response = server_error(request)
    assert response.status_code == 500

    response = server_error(request, template_name='non-existing.html')
    assert response.status_code == 500
