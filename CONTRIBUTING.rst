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

See the testing documentation at https://tecken.readthedocs.io/en/latest/dev.html .
