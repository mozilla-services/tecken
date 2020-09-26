# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib import admin
from django.contrib.admin import sites


class TeckenAdminSite(sites.AdminSite):
    index_template = "admin/tecken_admin_index.html"


site = TeckenAdminSite()

# Stomp on the myriad of places Django stashes their AdminSite instance so
# registering works with ours
admin.site = site
sites.site = site

# Autodiscover all the admin modules and pull in models and such
admin.autodiscover_modules("admin", register_to=site)
