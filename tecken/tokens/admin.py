# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib import admin

from tecken.tokens.models import Token


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = [
        "user_email",
        "expires_at",
        "created_at",
    ]

    def user_email(self, obj):
        return obj.user.email
