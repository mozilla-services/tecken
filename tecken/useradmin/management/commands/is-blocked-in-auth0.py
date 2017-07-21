# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from urllib.parse import urlparse

import requests

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tecken.useradmin.middleware import find_users


class Command(BaseCommand):
    help = 'Create or toggle an existing user being a superuser.'

    def add_arguments(self, parser):
        parser.add_argument('email')

    def handle(self, *args, **options):
        email = options['email']
        if ' ' in email or email.count('@') != 1:
            raise CommandError(f'Invalid email {email!r}')
        users = find_users(
            settings.OIDC_RP_CLIENT_ID,
            settings.OIDC_RP_CLIENT_SECRET,
            urlparse(settings.OIDC_OP_USER_ENDPOINT).netloc,
            email,
            requests,
        )
        for user in users:
            if user.get('blocked'):
                self.stdout.write(self.style.ERROR('BLOCKED!'))
            else:
                self.stdout.write(self.style.SUCCESS('NOT blocked!'))
            break
        else:
            self.stdout.write(self.style.WARNING(
                f'{email} could not be found in Auth0'
            ))
