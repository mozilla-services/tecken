# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.urls import path

from . import views


app_name = "api"
urlpatterns = [
    path("_auth/", views.auth, name="auth"),
    path("stats/", views.stats, name="stats"),
    path("syminfo/<str:some_file>/<hex:some_id>", views.syminfo, name="syminfo"),
    path("tokens/", views.tokens, name="tokens"),
    path("tokens/token/<int:id>/extend", views.extend_token, name="extend_token"),
    path("tokens/token/<int:id>", views.delete_token, name="delete_token"),
    path("uploads/", views.uploads, name="uploads"),
    path("uploads/files/", views.upload_files, name="upload_files"),
    path("uploads/files/file/<int:id>", views.upload_file, name="upload_file"),
    path("uploads/upload/<int:id>", views.upload, name="upload"),
]
