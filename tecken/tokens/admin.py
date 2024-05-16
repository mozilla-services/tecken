# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib import admin

from tecken.tokens.models import Token


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = [
        "key_truncated",
        "get_user_email",
        "get_permissions",
        "expires_at",
        "notes",
    ]

    list_filter = ["permissions"]
    search_fields = ["user__email", "notes"]

    @admin.display(description="Key")
    def key_truncated(self, obj):
        return obj.key[:12] + "..."

    @admin.display(description="Permissions")
    def get_permissions(self, obj):
        return ", ".join(perm.codename for perm in obj.permissions.all())

    @admin.display(description="Email")
    def get_user_email(self, obj):
        return obj.user.email
