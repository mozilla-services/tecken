# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Generated by Django 2.2.12 on 2020-05-28 00:54

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("download", "0005_msdownload_on_delete_null_upload"),
    ]

    operations = [
        migrations.DeleteModel(
            name="MicrosoftDownload",
        ),
    ]
