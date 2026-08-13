# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Django originally generated this migration as
#
#     class Migration(migrations.Migration):
#         dependencies = [
#             ("upload", "0025_bug_2049671_fileupload_created_at"),
#         ]
#         operations = [
#             migrations.AddConstraint(
#                 model_name="fileupload",
#                 constraint=models.UniqueConstraint(
#                     fields=("upload", "key"), name="upload_fileupload_upload_key_unique"
#                 ),
#             ),
#         ]
#
# This would have resulted in SQL code to directly add the uniqueness constraint to the table,
# which in turn would have required an exclusive lock on the table for the whole time it takes
# to create the index. To avoid having to take Tecken down for this migration, it was rewritten
# with the low-level `SeparateDatabaseAndState` operation to allow explicitly specifying the
# desired SQL instructions.

from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("upload", "0025_bug_2049671_fileupload_created_at"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "CREATE UNIQUE INDEX CONCURRENTLY "
                        '"upload_fileupload_upload_key_unique" '
                        'ON "upload_fileupload" ("upload_id", "key")'
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql=(
                        "SET statement_timeout = '1min'; "
                        'ALTER TABLE "upload_fileupload" '
                        'ADD CONSTRAINT "upload_fileupload_upload_key_unique" '
                        "UNIQUE USING INDEX "
                        '"upload_fileupload_upload_key_unique"; '
                        "RESET statement_timeout"
                    ),
                    reverse_sql=(
                        'ALTER TABLE "upload_fileupload" '
                        'DROP CONSTRAINT "upload_fileupload_upload_key_unique"'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="fileupload",
                    constraint=models.UniqueConstraint(
                        fields=("upload", "key"),
                        name="upload_fileupload_upload_key_unique",
                    ),
                ),
            ],
        ),
    ]
