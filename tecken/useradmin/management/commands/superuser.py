# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from mozilla_django_oidc.utils import import_from_settings
from mozilla_django_oidc.auth import default_username_algo


class Command(BaseCommand):
    help = "Create or toggle an existing user being a superuser."

    def add_arguments(self, parser):
        parser.add_argument("email", default=None, nargs="?")

    def handle(self, *args, **options):
        email = options["email"]
        if not email:
            email = input("Email: ").strip()
        if " " in email or email.count("@") != 1:
            raise CommandError(f"Invalid email {email!r}")
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            username_algo = import_from_settings("OIDC_USERNAME_ALGO", None)
            if username_algo:
                username = username_algo(email)
            else:
                username = default_username_algo(email)
            user = User.objects.create(username=username, email=email)
            user.set_unusable_password()
            self.stdout.write(self.style.WARNING("New user created"))

        if user.is_superuser and user.is_staff:
            self.stdout.write(self.style.WARNING(f"{email} already a superuser/staff"))
        else:
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            user.save()
            if user.is_superuser:
                self.stdout.write(
                    self.style.SUCCESS(f"{email} PROMOTED to superuser/staff")
                )
