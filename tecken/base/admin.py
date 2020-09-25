# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib import admin
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.auth.models import User
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
