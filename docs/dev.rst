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

Local development
=================

You run everything in Docker with:

.. code-block:: shell

    $ make build  # only needed once
    $ make run

This will start a server that is exposed on port ``8000`` so now you can
reach ``http://localhost:8000`` with your browser or curl.

Documentation
=============

Documentation is compiled with Sphinx_ and is available on ReadTheDocs.
API is automatically extracted from docstrings in the code.

To build the docs, run this:

.. code-block:: shell

    $ make docs

This is the same as running:

.. code-block:: shell

    $ docker-compose run web ./bin/build_docs.sh

To iterate on writing docs and testing that what you type compiles correctly,
run the above mentioned command on every save and then open the file
``docs/_build/html/index.html``. E.g.

.. code-block:: shell

    # the 'open' command is for OSX
    $ open docs/_build/html/index.html


.. _Sphinx: http://www.sphinx-doc.org/en/stable/

Hyperactive Document Writing
============================

If you write a lot and want to see the changes much sooner after having
written them, you can temporarily enter a shell and run exactly the
minimum needed. First start a shell and install the Python requirements:

.. code-block:: shell

   $ make test
   > pip install -r docs-requirements.txt

Now, you can run the command manually with just...:

.. code-block:: shell

   > make -C docs html

And keep an browser open to the file ``docs/_build/html/index.html`` in
the host environment.

If you're really eager to have docs built as soon as you save the ``.rst``
file in your editor, run this command:

.. code-block:: shell

   > watchmedo shell-command -W -c 'make -C docs html' -R .

Note that if you make a change/save *during* the build, it will ignore that.
So wait until it has finished before you save again. Note, that the ``.rst``
file you're working on doesn't actually need to change. A save-file is enough.

Also note that it won't build the docs until there has been at least one
file save.

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
   > py.test

   <pytest output>

   > py.test tests/test_symbolicate.py


We're using py.test_ for a test harness and test discovery.

.. _py.test: http://pytest.org/


Hyperactive Test Running
========================

If you want to make tests run as soon as you save a file you have to
enter a shell and run ``ptw`` which is a Python package that is
automatically installed when you enter the shell. For example:

.. code-block:: shell

   $ make shell
   > ptw

That will re-run ``py.test`` as soon as any of the files change.
If you want to pass any other regular options to ``py.test`` you can
after ``--`` like this:

.. code-block:: shell

  $ make shell
  > ptw -- -x --other-option


Python Requirements
===================

All Python requirements needed for development and production needs to be
listed in ``requirements.txt`` with sha256 hashes.

The most convenient way to modify this is to run ``hashin`` in a shell.
For example:

.. code-block:: shell

   $ make shell
   > pip install hashin
   > hashin Django==1.10.99
   > hashin other-new-package

This will automatically update your ``requirements.txt`` but it won't
install the new packages. To do that, you need to exit the shell and run:

.. code-block:: shell

   $ make build


To check which Python packages are outdated, use `piprot`_ in a shell:

.. code-block:: shell

   $ make shell
   > pip install piprot
   > piprot -o

The ``-o`` flag means it only lists requirements that are *out of date*.

.. note:: A good idea is to install ``hashin`` and ``piprot`` globally
   on your computer instead. It doesn't require a virtual environment if
   you use `pipsi`_.

.. _piprot: https://github.com/sesh/piprot
.. _pipsi: https://github.com/mitsuhiko/pipsi

Running ``gunicorn`` locally
============================

To run ``gunicorn`` locally, which has concurrency, run:

.. code-block:: shell

   $ make gunicorn

You might want to temporarily edit ``.env`` and set ``DJANGO_DEBUG=False``
to run it in a more production realistic way.
