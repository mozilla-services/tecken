# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib import admin
from admin_cursor_paginator import CursorPaginatorAdmin

from tecken.upload.models import Upload, FileUpload


@admin.register(Upload)
class UploadAdmin(CursorPaginatorAdmin):
    date_hierarchy = "created_at"
    search_fields = ["user.email", "bucket_name"]
    list_display = [
        "id",
        "user_email",
        "try_symbols",
        "download_by_upload",
        "bucket_name",
        "size",
        "created_at",
    ]

    view_on_site = True

    def user_email(self, obj):
        return obj.user.email

    def download_by_upload(self, obj):
        return bool(obj.download_url)


@admin.register(FileUpload)
class FileUploadAdmin(CursorPaginatorAdmin):
    readonly_fields = [
        "upload",
    ]
    date_hierarchy = "created_at"
    search_fields = ["key", "debug_id", "debug_filename", "code_id", "code_file"]
    list_display = ["id", "upload_id", "bucket_name", "key", "size", "created_at"]

    view_on_site = True
