# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib.auth.models import Permission, User
from django.core.management.base import BaseCommand, CommandError

from tecken.tokens.models import make_key, Token


class Command(BaseCommand):
    help = "Create an API token."

    def add_arguments(self, parser):
        parser.add_argument("email", default=None, nargs="?")
        parser.add_argument("token_key", default=None, nargs="?")

    def handle(self, *args, **options):
        email = options["email"]
        if not email:
            email = input("Email: ").strip()
        if " " in email or email.count("@") != 1:
            raise CommandError(f"Invalid email {email!r}")

        token_key = options["token_key"]
        if not token_key:
            token_key = make_key()

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise CommandError(f"Account {email!r} does not exist.") from None

        if Token.objects.filter(user=user, key=token_key).exists():
            raise CommandError(f"Token with key {token_key!r} already exists")

        permissions = [
            Permission.objects.get(codename="upload_symbols"),
            Permission.objects.get(codename="view_all_uploads"),
        ]
        self.stdout.write(self.style.SUCCESS(f"{token_key} created"))
        token = Token.objects.create(
            user=user,
            key=token_key,
        )
        for permission in permissions:
            token.permissions.add(permission)
            self.stdout.write(self.style.SUCCESS(f"{permission} added"))
