============
Contributing
============

Code of Conduct
===============

This project and repository is governed by Mozilla's code of conduct and
etiquette guidelines. For more details please see the `CODE_OF_CONDUCT.md file
<https://github.com/mozilla-services/tecken/blob/main/CODE_OF_CONDUCT.md>`_.


Bugs
====

All bugs are tracked in `<https://bugzilla.mozilla.org/>`_.

Write up a new bug:

https://bugzilla.mozilla.org/enter_bug.cgi?product=Tecken&component=General

If you want to do work for which there is no bug, it's best to write up a bug
first. Maybe the ensuing conversation can save you the time and trouble
of making changes!


Pull requests
=============

Pull request summary should indicate the bug the pull request addresses. For
example::

  bug NNNNNNN: removed frob from tree class

Pull request descriptions should cover at least some of the following:

1. what is the problem the pull request is addressing?
2. why does this pull request fix the issue?
3. what did you do to test the changes?
4. any steps-to-reproduce for the reviewer to use to test the changes
5. any special instructions or things you want the reviewer to check out


Code reviews
============

Pull requests should be reviewed before merging.

Style nits should be covered by linting as much as possible.

Code reviews should review the changes in the context of the rest of the system.


Preparing to contribute changes to Tecken
=========================================

If you're interested in helping out and taking a bug to work on, you
need to do the following first:

1. `Set up a working local development environment
   <https://tecken.readthedocs.io/en/latest/dev.html>`_.

2. Read through the `Tecken docs <https://tecken.readthedocs.io/>`_.

We can't assign bugs to you until you've done at least those two
steps.


Conventions
===========

Python code conventions
-----------------------

All Python code files should have an MPL v2 header at the top::

  # This Source Code Form is subject to the terms of the Mozilla Public
  # License, v. 2.0. If a copy of the MPL was not distributed with this
  # file, You can obtain one at http://mozilla.org/MPL/2.0/.


We use `black <https://black.readthedocs.io/en/stable/>`_ to reformat Python
code and we use `prettier <https://prettier.io/>`_ to reformat JS code.


To lint all the code, do:

.. code-block:: bash

  $ make lint


To reformat all the code, do:

.. code-block:: bash

  $ make lintfix


HTML/CSS conventions
--------------------

2-space indentation.


Javascript code conventions
---------------------------

2-space indentation.

All JavaScript code files should have an MPL v2 header at the top::

  /*
   * This Source Code Form is subject to the terms of the Mozilla Public
   * License, v. 2.0. If a copy of the MPL was not distributed with this
   * file, You can obtain one at http://mozilla.org/MPL/2.0/.
   */


Git conventions
---------------

First line is a summary of the commit. It should start with::

  bug nnnnnnn: summary


After that, the commit should explain *why* the changes are being made and any
notes that future readers should know for context or be aware of.


Database migrations
===================

We use Django's ORM and thus we do database migrations using Django's
migration system.

Do this::

    $ make shell
    app@xxx:/app$ ./manage.py makemigration --name "BUGID_desc" APP


Managing dependencies
=====================

Python dependencies
-------------------

Python dependencies for all parts of Socorro are split between two files:

1. ``requirements/default.txt``, containing dependencies that Socorro uses
   directly.
2. ``requirements/constraints.txt``, containing dependencies required by the
   dependencies in ``default.txt`` that Socorro does not use directly.

Dependencies in both files must be pinned and hashed. Use
`hashin <https://pypi.python.org/pypi/hashin>`_.

For example, to add ``foobar`` version 5::

  $ hashin -r requirements/default.txt foobar==5

If ``foobar`` has any dependencies that would also be installed, you must add
them to the constraints file::

  $ hashin -r requirements/constraints.txt bazzbiff==4.0

Then rebuild your docker environment::

  $ make build

If there are problems, it'll tell you.

.. Note::

   If you're unsure what dependencies to add to the constraints file, the error
   from running ``make build`` should include a list of dependencies that were
   missing, including their version numbers and hashes.


JavaScript dependencies
-----------------------

Tecken uses `yarn <https://yarnpkg.com/>`_ for JavaScript dependencies. Use the
``yarn`` installed in the Docker frontend container:

.. code-block:: shell

    $ docker-compose run frontend bash

    # display packages that can be upgraded
    node@xxx:/app$ yarn outdated

    # example of upgrading an existing package
    node@xxx:/app$ yarn upgrade date-fns --latest

    # example of adding a new package
    node@xxx:/app$ yarn add some-new-package

When you're done, you have to rebuild the frontend Docker container:

.. code-block:: shell

    $ docker-compose build frontend

Your change should result in changes to ``frontend/package.json`` *and*
``frontend/yarn.lock`` which needs to both be checked in and committed.


Documentation
=============

Documentation for Tecken is build with `Sphinx
<http://www.sphinx-doc.org/>`_ and is available on ReadTheDocs.

To build the docs, do:

.. code-block:: shell

  $ make docs

Then view ``docs/_build/html/index.html`` in your browser.


Testing
=======

Unit tests
----------

Tecken uses `pytest <https://pytest.org/>`_ for unit tests.

To run the tests, do:

.. code-block:: shell

   $ make test

Tests go in ``tests/``. Data required by tests goes in ``tests/data/``.

If you need to run specific tests or pass in different arguments, you can use
the testshell:

.. code-block:: shell

   $ make testshell
   app@xxx:/app$ pytest

   <pytest output>

   app@xxx:/app$ pytest tests/test_symbolicate.py


System tests
------------

System tests are located in ``systemtests/``. See the ``README.rst`` there for
usage.

System tests can be run against any running environment: local, stage, or prod.


Frontend JavaScript tests
-------------------------

There are no tests for the JavaScript code. For now, run the app and click
through the site:

1. go to website
2. wait for front page to load
3. click on "Home"
4. click on "Downloads missing"
5. click on "Symbolication"
6. click on "Help"
7. click on "Log in" and log in
8. click on "Home"
9. click on "Downloads missing"
10. click on "User management"
11. click on "API tokens"
12. click on "Uploads"
13. click on "Symbolication"
14. click on "Help"
15. click on "Sign out"
