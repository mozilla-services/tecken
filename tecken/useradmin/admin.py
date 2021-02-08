# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from tecken.tokens.models import Token
from tecken.upload.models import Upload


# Unregister the original UserAdmin and register our better one
try:
    admin.site.unregister(User)
except TypeError:
    pass


@admin.register(User)
class UserAdminBetter(UserAdmin):
    """Improved UserAdmin."""

    list_display = [
        "email",
        "is_active",
        "num_uploads",
        "num_api_tokens",
        "last_upload",
        "in_groups",
        "is_superuser",
        "is_staff",
        "date_joined",
        "last_login",
    ]

    def in_groups(self, obj):
        """Return comma-separated list of groups this user is in."""
        return ", ".join(obj.groups.values_list("name", flat=True))

    in_groups.short_description = "Groups"

    def num_uploads(self, obj):
        return Upload.objects.filter(user=obj).count()

    num_uploads.short_description = "# Uploads"

    def last_upload(self, obj):
        """Returns most recent upload date or None."""
        data = (
            Upload.objects.filter(user=obj)
            .order_by("-completed_at")
            .values_list("completed_at", flat=True)
            .first()
        )
        return data

    last_upload.short_description = "Last upload"

    def num_api_tokens(self, obj):
        return Token.objects.filter(user=obj).count()

    num_api_tokens.short_description = "# Tokens"
