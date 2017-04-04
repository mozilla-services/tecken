=======================
Developer Documentation
=======================

Code
====

All code files need to start with the MPLv2 header::

    # This Source Code Form is subject to the terms of the Mozilla Public
    # License, v. 2.0. If a copy of the MPL was not distributed with this
    # file, You can obtain one at http://mozilla.org/MPL/2.0/.

PEP8 is nice. All files are expected to be PEP8 and pyflakes compliant
and the PEP8 rules (and exceptions) are defined in ``setup.cfg`` under
the ``[flake8]`` heading.

The tests use ``py.test`` with a plugin called ``flake8`` which will
check files according to the flake8 rules as it runs tests.

If you hit issues, instead of re-writing the rules consider
appending a comment on the end of the line that says ``# noqa``.

Documentation
=============

Documentation is compiled with Sphinx_ and is available on ReadTheDocs.
API is automatically extracted from docstrings in the code.

To build the docs, run this:

.. code-block:: shell

    $ make docs


.. _Sphinx: http://www.sphinx-doc.org/en/stable/


Testing
=======

To run the tests, run this:

.. code-block:: shell

   $ make test


Tests go in ``tests/``. Data required by tests goes in ``tests/data/``.

If you need to run specific tests or pass in different arguments, you can run
bash in the base container and then run ``py.test`` with whatever args you
want. For example:

.. code-block:: shell

   $ make shell
   # py.test

   <pytest output>

   # py.test tests/test_symbolicate.py

For development it might be convenient to iterate quickly so that tests
are run immediately as soon as files are saved in your editor. To do,
start the shell like this:

.. code-block:: shell

   $ make shell
   # pip install pytest-watch
   # ptw

That will re-run ``py.test`` as soon as any of the files change.
If you want to pass any other regular options to ``py.test`` you can
after ``--`` like this:

.. code-block:: shell

   $ make shell
   # pip install pytest-watch
   # ptw -- -x --other-option


We're using py.test_ for a test harness and test discovery.

.. _py.test: http://pytest.org/


Python Requirements
===================

All Python requirements needed for development and production needs to be
listed in ``requirements.txt`` with sha256 hashes.

The most convenient way to modify this is to run ``hashin`` in a shell.
For example:

.. code-block:: shell

   $ make shell
   # hashin Django==1.10.99
   # hashin other-new-package

This will automatically update your ``requirements.txt`` but it won't
install the new packages. To do that, you need to exit the shell and run:

.. code-block:: shell

   $ make build


To check which Python packages are outdated, use `piprot`_ in a shell:

.. code-block:: shell

   $ make shell
   # pip install piprot
   # piprot -o

The ``-o`` flag means it only lists requirements that are *out of date*.

.. _piprot: https://github.com/sesh/piprot
