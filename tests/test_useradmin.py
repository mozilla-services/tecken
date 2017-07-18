# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from io import StringIO

import pytest

from django.core.management.base import CommandError
from django.contrib.auth.models import User
from django.core.management import call_command


@pytest.mark.django_db
def test_superuser_command():
    stdout = StringIO()
    call_command(
        'superuser',
        'foo@example.com',
        interactive=False,
        stdout=stdout,
    )
    output = stdout.getvalue()
    assert 'User created' in output
    assert 'PROMOTED to superuser' in output
    assert User.objects.get(email='foo@example.com', is_superuser=True)

    # all it a second time
    stdout = StringIO()
    call_command(
        'superuser',
        'foo@example.com',
        interactive=False,
        stdout=stdout,
    )
    output = stdout.getvalue()
    assert 'User created' not in output
    assert 'DEMOTED to superuser' in output
    assert User.objects.get(email='foo@example.com', is_superuser=False)

    with pytest.raises(CommandError):
        stdout = StringIO()
        call_command(
            'superuser',
            'gibberish',
            interactive=False,
            stdout=stdout,
        )
