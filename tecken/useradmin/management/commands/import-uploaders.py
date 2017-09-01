# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import sys
import json

from django.contrib.auth.models import User, Group
from django.core.management.base import BaseCommand

from mozilla_django_oidc.utils import import_from_settings
from mozilla_django_oidc.auth import default_username_algo

from tecken.tokens.models import Token


class Command(BaseCommand):
    """
    This import command is basically just to serve us as we migrate
    users (and their API tokens) from Socorro to Tecken. Once we've done
    this and the dust has settled. This file can be deleted.

    Usage:

        $ cat users.json
        {
           "peterbe@example.com": [
             {
                 "key": "secret",
                 "notes": "Some notes",
                 "expires": "2025-06-29T18:46:19.228Z"
             }
           ],
        }
        $ docker-compose run web python manage.py import-uploaders < users.json

    The work of doing the migration is covered in:
    https://bugzilla.mozilla.org/show_bug.cgi?id=1395647
    """

    help = (
        'One-off script (that you can run repeatedly) for importing '
        'symbol uploader users from crash-stats.mozilla.com'
    )

    def add_arguments(self, parser):
        parser.add_argument('jsonfile', nargs='?')

    def handle(self, *args, **options):
        jsonfile = options['jsonfile']
        if jsonfile:
            with open(jsonfile) as f:
                users = json.load(f)
        else:
            # Reading from stdin is convenient since the host and
            # docker don't necessary share filesystem.
            users = json.load(sys.stdin)

        from pprint import pprint
        pprint(users)

        uploaders = Group.objects.get(name='Uploaders')

        for email in users:
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                username_algo = import_from_settings(
                    'OIDC_USERNAME_ALGO',
                    None
                )
                if username_algo:
                    username = username_algo(email)
                else:
                    username = default_username_algo(email)
                user = User.objects.create(
                    username=username,
                    email=email,
                )
                user.set_unusable_password()
                self.stdout.write(self.style.WARNING(
                    f'User created ({user.email})'
                ))

                # Put the user in the Uploaders group so they can have
                # the right permissions they need when they generate
                # their API tokens.
                user.groups.add(uploaders)

            tokens = users[email]
            if not tokens:
                self.stdout.write(self.style.WARNING(
                    f'{user.email} has no active API tokens'
                ))
            for token in tokens:
                if Token.objects.filter(user=user, key=token['key']):
                    continue
                Token.objects.create(
                    user=user,
                    key=token['key'],
                    notes=token['notes'],
                    expires_at=token['expires']
                )
