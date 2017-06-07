# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_for_missing_migrations():
    output = StringIO()
    try:
        call_command(
            'makemigrations',
            interactive=False,
            check=True,
            stdout=output,
        )
    except SystemExit as exc:
        # The exit code will be 0 when there are no missing migrations
        assert exc.code == 1
        pytest.fail("There are missing migrations:\n %s" % output.getvalue())
