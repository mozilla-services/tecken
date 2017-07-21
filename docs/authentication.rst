==============
Authentication
==============

We use Auth0 to handle all authentication. See :ref:`Auth0 configuration <auth0-configuration>`.

Authentication **will let anybody** become a signed in user. But note, the
user will **not have any useful permissions** to do anything more than
anonymous users can do. That is, until someone uses the user administration
to elevate this user's permissions.


Auth0 Blocked
=============

A potential pattern is that a user logs in with their work email
(e.g. ``example@mozilla.com``), gets permissions to create API tokens,
the uses the API tokens in a script and later *leaves* the company whose
email she *used* she can no longer sign in to again. If this happens
her API token should cease to work, because it was created based on the
understanding that she was an employee and has access to the email address.

This is why there's a piece of middleware that periodically checks that
users who once authenticated with Auth0 still is there and **not blocked**.

Being "blocked" in Auth0 is what happens, "internally", if a user is removed
from LDAP/Workday and Auth0 is informed. There could be other reasons why
a user is blocked in Auth0. Whatever the reasons, users who are blocked
immediately become inactive and logged out if they're logged in.

If it was an error, the user can try to log in again and if that works,
the user becomes active again.

This check is done (at the time of writing) max. every 24 hours. Meaning,
if you managed to sign or use an API token, you have 24 hours to use this
cookie/API token till your user account is checked again in Auth0. To
override this interval change the environment variable
``DJANGO_NOT_BLOCKED_IN_AUTH0_INTERVAL_SECONDS``.

Testing Blocked
===============

To check if a user is blocked, use the ``is-blocked-in-auth0`` which is
development tool shortcut for what the middleware does:

.. code-block:: shell

    $ docker-compose run web python manage.py is-blocked-in-auth0 me@example.com
