# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Generated by Django 3.2.16 on 2022-10-19 19:56

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("upload", "0019_auto_20180831_1345"),
    ]

    operations = [
        migrations.AlterField(
            model_name="upload",
            name="size",
            field=models.PositiveBigIntegerField(),
        ),
    ]
