==========
Deployment
==========

.. contents::

Environments
============

Mozilla Symbol Server is deployed in 3 different environments:

1. Production (https://symbols.mozilla.org SOON!)

2. Stage (https://symbols.stage.mozaws.net)

3. Dev (https://symbols.dev.mozaws.net)

The stage and production environments are only updated at manual and
discrete points by the team. The dev environment is always up-to-date
with the latest version (i.e. master on GitHub).

All (manual) testing of features is expected to be done on the
dev environment.


Tagging
=======

Code is pushed to GitHub. On every push, CircleCI_ builds a
"latest" build to `Docker Hub`_ as well as one based on the CircleCI
build number and one based on any git tags.

Git tagging is done manually by the team. The expected format is something
like this::

    git tag -s -a 2017.04.17 -m "Message about this release"

The tag format isn't particularly important but it's useful to make it
chronological in nature so it's easy to compare tags without having
to dig deeper. The format is a date, but if there are more tags
made on the same date, append a hyphen and a number. For example::

    git tag -s -a 2017.04.17-2 -m "Fix for sudden problem"

.. _CircleCI: https://circleci.com/gh/mozilla-services/tecken
.. _`Docker Hub`: https://hub.docker.com/r/mozilla/tecken/

Automation
==========

To make a tag run:

.. code-block:: shell

   $ make tag

and it will guide you through create a git tag and having that pushed.

Stage and production deployment requires that the development team
communicates the desired git tag name to the Cloud OPs team.
(MORE DETAILS ABOUT THIS TO COME)
