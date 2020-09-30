# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import json
from urllib.parse import urlparse, urlunparse

from dockerflow.version import get_version as dockerflow_get_version
from django_redis import get_redis_connection

from django import get_version
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db import connection
from django.shortcuts import render
from django.urls import reverse, NoReverseMatch
from django.utils.html import format_html


ACTION_TO_NAME = {ADDITION: "add", CHANGE: "change", DELETION: "delete"}


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    date_hierarchy = "action_time"

    list_display = [
        "action_time",
        "admin",
        "object_link",
        "action",
        "get_change_message",
    ]
    list_display_links = ["action_time", "get_change_message"]

    def admin(self, obj):
        return obj.user.email

    def action(self, obj):
        return ACTION_TO_NAME[obj.action_flag]

    def obj_repr(self, obj):
        edited_obj = obj.get_edited_object()

        if isinstance(edited_obj, User):
            # For user objects, return the email address as an identifier
            return edited_obj.email
        return edited_obj

    def object_link(self, obj):
        object_link = self.obj_repr(obj)  # Default to just name
        content_type = obj.content_type

        if obj.action_flag != DELETION and content_type is not None:
            # try returning an actual link instead of object repr string
            try:
                url = reverse(
                    "admin:{}_{}_change".format(
                        content_type.app_label, content_type.model
                    ),
                    args=[obj.object_id],
                )
                object_link = format_html('<a href="{}">{}</a>', url, object_link)
            except NoReverseMatch:
                pass
        return object_link

    object_link.admin_order_field = "object_repr"
    object_link.short_description = "object"

    def get_change_message(self, obj):
        return obj.get_change_message()

    get_change_message.short_description = "change message"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@login_required(login_url="/")
@user_passes_test(lambda user: user.is_active and user.is_staff, login_url="/")
def site_status(request):
    context = {"settings": [], "table counts": [], "versions": []}

    # Figure out settings first
    def clean_url(value):
        parsed = urlparse(value)
        if "@" in parsed.netloc:
            # There might be a password in the netloc part.
            # It's extremely unlikely but just in case we ever forget
            # make sure it's never "exposed".
            parts = list(parsed)
            parts[1] = "user:xxxxxx@" + parts[1].split("@", 1)[1]
            return urlunparse(parts)
        return value

    # Only include keys that can never be useful in security context.
    keys = (
        "ENABLE_AUTH0_BLOCKED_CHECK",
        "ENABLE_TOKENS_AUTHENTICATION",
        "ALLOW_UPLOAD_BY_DOWNLOAD_DOMAINS",
        "DOWNLOAD_FILE_EXTENSIONS_ALLOWED",
        "ENABLE_STORE_MISSING_SYMBOLS",
    )
    for key in keys:
        value = getattr(settings, key)
        context["settings"].append({"key": key, "value": value})

    # Now for some oddballs
    context["settings"].append(
        {"key": "UPLOAD_DEFAULT_URL", "value": clean_url(settings.UPLOAD_DEFAULT_URL)}
    )
    context["settings"].append(
        {
            "key": "UPLOAD_TRY_SYMBOLS_URL",
            "value": clean_url(settings.UPLOAD_TRY_SYMBOLS_URL),
        }
    )
    context["settings"].append(
        {
            "key": "SYMBOL_URLS",
            "value": json.dumps([clean_url(x) for x in settings.SYMBOL_URLS]),
        }
    )
    context["settings"].append(
        {
            "key": "UPLOAD_URL_EXCEPTIONS",
            "value": json.dumps(
                {k: clean_url(v) for k, v in settings.UPLOAD_URL_EXCEPTIONS.items()}
            ),
        }
    )
    context["settings"].sort(key=lambda x: x["key"])

    # Get some table counts
    tables = [
        "download_missingsymbol",
        "upload_upload",
        "upload_fileupload",
        "upload_uploadscreated",
    ]
    context["table_counts"] = []
    for table_name in tables:
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from %s" % table_name)
            row = cursor.fetchone()
            (value,) = row
        context["table_counts"].append({"key": table_name, "value": value})

    # Now get versions
    with connection.cursor() as cursor:
        cursor.execute("select version()")
        row = cursor.fetchone()
        (value,) = row
        context["versions"].append(
            {
                "key": "PostgreSQL",
                "value": value.split(" on ")[0].replace("PostgreSQL", "").strip(),
            }
        )
    context["versions"].append(
        {"key": "Tecken", "value": dockerflow_get_version(settings.BASE_DIR)}
    )
    context["versions"].append({"key": "Django", "value": get_version()})
    redis_store_info = get_redis_connection("store").info()
    context["versions"].append(
        {"key": "Redis Store", "value": redis_store_info["redis_version"]}
    )
    try:
        redis_cache_info = get_redis_connection("default").info()
    except NotImplementedError:
        redis_cache_info = {"redis_version": "fakeredis"}
    context["versions"].append(
        {"key": "Redis Cache", "value": redis_cache_info["redis_version"]}
    )

    context["versions"].sort(key=lambda x: x["key"])

    return render(request, "admin/site_status.html", context)
