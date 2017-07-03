=======================
Developer Documentation
=======================

Code
====

All code files need to start with the MPLv2 header::

    # This Source Code Form is subject to the terms of the Mozilla Public
    # License, v. 2.0. If a copy of the MPL was not distributed with this
    # file, You can obtain one at http://mozilla.org/MPL/2.0/.

To check if any file is lacking a license preamble, run:

.. code-block:: shell

    $ ./bin/sanspreamble

It will exit non-zero if there are files lacking the preamble. It only
checks git checked in files.

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


Development Metrics for Symbolication
=====================================

When you run the server in development mode, it's configured to log every
cache miss and cache hit, not only to ``statsd`` but also storing it
in the cache framework. This makes it possible to query the metrics
insight view:

.. code-block:: shell

   $ curl http://localhost:8000/symbolicate/metrics

That gives you numbers about what the metrics are up to right now.

The best way to visualize this is to start the ``metricsapp`` which
is a simple single-page-app that reads this above mentioned URL
repeatedly and draws graphs. It also helps you understand how the
LRU cache works.

To start the ``metricsapp`` do:

.. code-block:: shell

   $ cd metricsapp
   $ yarn  # Only needed the first time!
   $ yarn start

Then go to ``http://localhost:3000/`` and keep watching it as you
do more and more symbolication requests locally.

Manual Integration Testing for symbolication
============================================

To do integration testing pasting lots of ``curl`` commands gets
tedious. Instead use `tecken-loader`_. It's a simple script that
sends symbolication requests to your local server. Run this in a separate
terminal when you have started the development server:

.. code-block:: shell

   $ git clone https://github.com/peterbe/tecken-loader.git
   $ cd tecken-loader
   $ python3.5 main.py stacks http://localhost:8000/

It will keep going to ages. If you kill it with ``Ctrl-C`` it will
print out a summary of what it has done.

This is useful for sending somewhat realistic symbolication requests
that reference symbols that are often slightly different.

.. _`tecken-loader`: https://github.com/peterbe/tecken-loader


Testing Statsd
==============

By default, the docker image starts a Graphite server that metrics are
sent to. You can run it locally by visiting ``http://localhost:9000``.

A much better interface for local development is to start a Grafana_
server. When you run it locally, note that you will be asked to log in
and the username is ``admin`` and password ``admin``. This is safe because
it's an Grafana instance only on your laptop. To start it:

.. code-block:: shell

    $ docker run -i -p 3000:3000 grafana/grafana
    $ open http://localhost:3000

Explaining all of Grafana is hard and they have direct links to the
documentation within the UI.

The first thing to do is to create a "Data Source" for Graphite. The
only parameter you need is the URL which should be ``http://localhost:9000``.

.. _Grafana: https://hub.docker.com/r/grafana/grafana/


Prod-like running locally
=========================

First you need to start Tecken with a set of configurations that
mimics what's required in prod, except we're doing this in docker.

To do that, you need to set ``DJANGO_CONFIGURATION=Prodlike`` and
run the gunicorn workers:

.. code-block:: shell

    $ docker-compose run --service-ports --user 0  web bash

This will start 4 ``gunicorn`` workers exposed on ``0.0.0.0:8000`` and
exposed outside of docker onto your host.

.. note:: If this fails to start, some exceptions might be hidden. If so,
          start a shell ``docker-compose run --user 0 web bash`` and run:
          ``DJANGO_UPLOAD_DEFAULT_URL=http://localstack-s3:4572/testbucket DJANGO_SYMBOL_URLS=http://localstack-s3:4572/testbucket DJANGO_CONFIGURATION=Prodlike gunicorn tecken.wsgi:application -b 0.0.0.0:8000 --workers 4 --access-logfile -``

That configuration **forces** you to run with ``DEBUG=False`` independent
of what value you have set in ``.env`` for ``DEBUG``. Thus making it easy
to switch from regular debug-mode development to prod-like serving.

The second step for this to be testable is to reach the server with ``HTTPS``
or else the app will forcibly redirect you to the ``https://`` equivalent of
whatever URL you attempt to use (e.g. ``http://localhost:8000/`` redirects
to ``https://localhost:8000/``)

To test this, run a local Nginx server. But first, create a suitable
hostname. For example, ``prod.tecken.dev``. Edit ``/etc/hosts`` and enter
a line like this::

    127.0.0.1       prod.tecken.dev

To generate an nginx config file, run ``./test-with-nginx/generate.py``.
That will be print out a Nginx configuration file you can put where
you normally put Nginx configuration files. For example:

.. code-block:: shell

    $ ./test-with-nginx/generate.py --help
    $ ./test-with-nginx/generate.py > /etc/nginx/sites-enabled/tecken.conf
    $ # however you reload nginx

System tests
============

System test aims to replace and be similar to doing manual testing with
your browser or ``curl``. They depend on the server being up and running
but will start a web server if it's not already running.

To start the system tests run:

.. code-block:: shell

    $ make systemtest

If you want to see the requests coming in in foreground logging, you can
start the server in another terminal first, and then run ``make systemtest``
in a second terminal.

If you need to do some debugging into a specific test with system tests,
it's tedious to have to run all the tests every time. One trick is to
take the command that ``make systemtest`` represents in ``Makefile``
and then run it with extra ``pytest`` parameters. For example:

.. code-block:: shell

    $ docker-compose run systemtest tests/systemtest/run_tests.sh -k test_delberately_404ing_and_csv_reporting

Shells and ``hack.py``
======================

There are a couple of good ways to get into the Python environment and
be able to "hack around" and try stuff. For example, you might want to just
poke around in the ORM, or test various performance tricks and as it
gets more complicated it gets messy in a shell. Especially if you want to
re-run something on multiple lines repeatedly.

Instead, copy the file ``hack.py-dist`` to ``hack.py`` and start editing it.
Then, to run it, start a shell and execute it:

.. code-block:: shell

    $ make shell
    # python hack.py
