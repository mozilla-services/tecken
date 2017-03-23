from io import StringIO

import pytest
from django.core.management import call_command


def test_for_missing_migrations():
    output = StringIO()
    try:
        call_command(
            'makemigrations', interactive=False, dry_run=True, exit_code=True,
            stdout=output)
    except SystemExit as exc:
        # The exit code will be 1 when there are no missing migrations
        assert exc.code == 1
    else:
        pytest.fail("There are missing migrations:\n %s" % output.getvalue())
