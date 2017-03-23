# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from urllib.parse import urlparse
import pytest
from django.contrib.sites.models import Site


@pytest.mark.django_db
def test_initial_site(settings):
    "Test if the site migration uses the env var SITE_URL"
    domain = urlparse(settings.SITE_URL)
    assert Site.objects.get_current().domain, domain.netloc
