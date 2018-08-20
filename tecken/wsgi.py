# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
"""
WSGI config for tecken project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/howto/deployment/wsgi/
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tecken.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "Localdev")

from configurations.wsgi import get_wsgi_application  # noqa

application = get_wsgi_application()

if "SENTRY_DSN" in os.environ:
    from raven.contrib.django.raven_compat.middleware.wsgi import Sentry

    application = Sentry(application)
