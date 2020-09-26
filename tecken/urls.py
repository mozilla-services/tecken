# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.urls import register_converter, path, include

from tecken.base import admin_site
from tecken import views

# These handlers are for dealing with exceptions raised from within
# Django. Most other 4xx errors happen explicitly in the view functions.
handler500 = "tecken.views.handler500"
handler400 = "tecken.views.handler400"
handler403 = "tecken.views.handler403"
handler404 = "tecken.views.handler404"


class FrontendRoutesPrefixConverter:
    regex = r"(users|tokens|help|uploads|symbolication|downloads|index\.html).*?"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(FrontendRoutesPrefixConverter, "frontendroutes")


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("__auth_debug__", views.auth_debug, name="auth_debug"),
    path("__task_tester__", views.task_tester, name="task_tester"),
    path("symbolicate/", include("tecken.symbolicate.urls", namespace="symbolicate")),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("upload/", include("tecken.upload.urls", namespace="upload")),
    path("api/", include("tecken.api.urls", namespace="api")),
    path("", include("tecken.download.urls", namespace="download")),
    path("contribute.json", views.contribute_json, name="contribute_json"),
    # Static pages in admin
    path("admin/", include("tecken.base.admin_urls", namespace="siteadmin")),
    # Django-model backed pages in admin
    path("admin/", admin_site.site.urls),
    path(
        "<frontendroutes:path>", views.frontend_index_html, name="frontend_index_html"
    ),
]
