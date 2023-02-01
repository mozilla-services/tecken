# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Generated by Django 1.11.4 on 2017-08-29 17:01

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("upload", "0007_upload_attempts"),
    ]

    operations = [
        migrations.AddField(
            model_name="upload",
            name="download_url",
            field=models.URLField(max_length=500, null=True),
        ),
    ]
