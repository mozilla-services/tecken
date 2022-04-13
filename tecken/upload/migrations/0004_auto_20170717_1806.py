# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Generated by Django 1.11.3 on 2017-07-17 18:06

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("upload", "0003_upload_ignored_keys"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="upload",
            options={
                "permissions": (
                    ("upload_symbols", "Upload Symbols Files"),
                    ("view_all_uploads", "View All Symbols Uploads"),
                )
            },
        ),
    ]
