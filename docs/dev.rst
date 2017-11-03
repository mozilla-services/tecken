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

    $ ./bin/sanspreamble.sh

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

It will keep going for ages. If you kill it with ``Ctrl-C`` it will
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
          ``DJANGO_UPLOAD_DEFAULT_URL=http://minio:9000/testbucket DJANGO_SYMBOL_URLS=http://minio:9000/testbucket DJANGO_CONFIGURATION=Prodlike gunicorn tecken.wsgi:application -b 0.0.0.0:8000 --workers 4 --access-logfile -``

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


Frontend and prod-like running locally
======================================

When Tecken is deployed with continuous integration, it builds the static
assets files for production use. These files are served by Django using
Whitenoise. Basically, anything that isn't a matched Django URL-to-view
gets served as a static file, if matched.

Suppose you want to run the prod-like frontend locally. For example, you
might be hunting a frontend bug that only happens when the assets are
minified and compiled. To do that you have to manually build the static assets:

.. code-block:: shell

    $ cd frontend
    $ yarn
    $ yarn run build

This should create ``frontend/build/*`` files. For example
``static/js/main.6d3b4de8.js``. This should now be available *thru* Django
at ``http://localhost:8000/static/js.main.6d3b4de8.js``.

When you're done you can delete ``frontend/build`` and
``frontend/node_modules``.

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


Running things in background vs foreground
==========================================

By default ``make run`` is wired to start three things in the foreground:

* Django (aka. ``web``)

* Celery (aka. ``worker``)

* React dev server (aka. ``frontend``)

This is done by running ``docker-compose up web worker frontend``. These
services' output is streamed together to stdout in the foreground that
this ``docker-compose up ...`` runs.

All other things that these depend on are run in the background. Meaning
you don't see, for example, what the ``minio`` service does. It knows to
*start* because in ``docker-compose.yml`` ``web`` is **linked** to
``minio``.

If you instead want to run, for example, ``minio`` in the foreground here's
how:

1. Comment out ``minio`` from the ``links`` part of ``web`` in ``docker-compose.yml``

2. In a terminal run ``docker-compose up minio``.

3. In another terminal run ``make run``

Alternatively, just do step 1, from the list above, and then run:
``docker-compose up minio web worker frontend``.


All metrics keys
================

To get insight into all metrics keys that are used, a special Markus backend
is enabled called ``tecken.markus_extra.LogAllMetricsKeys``. It's enabled
by default in local development. And to inspect its content you can either
open ``all-metrics-keys.json`` directly (it's git ignored) or you can run:

.. code-block:: shell

    $ make shell
    $ ./bin/list-all-metrics-keys.py

Now you can see a list of all keys that are used. Take this and, for example,
make sure you make a graph in Datadog of each and everyone. If there's a key
in there that you know you don't need or care about in Datadog, then delete
it from the code.

The file ``all-metrics-keys.json`` can be deleted any time and it will be
recreated again.


Celery in local development mode
================================

When you do something like ``make run`` it starts Django, the frontend
and the Celery worker. But it's important to note that it starts Celery
with ``--purge``. That means that every time you start up the worker,
all jobs that have been previously added to the Celery query are purged.

This is to prevent foot-shooting. Perhaps a rogue unit test that didn't mock
the broker and accidentally added hundreds of jobs that all fail.
Or perhaps you're working on a git branch that changes how the worker job
works and as you're jumping between git branches you start and stop the worker
so that the wrong jobs are sent using the wrong branch.

Another real thing that can happen is that when you're doing loadtesting of
the web app, and only run that in docker, but since the web app writes to
the same Redis (the broker) thousands of jobs might be written that never
get a chance to be consumed by the worker.

This is why ``docker-compose`` starts ``worker-purge`` instead of ``worker``
which is the same thing except it's started with ``--purge`` and this should
only ever be done on local docker development.


Minio (S3 mock server)
======================

When doing local development we, by default, mock AWS S3 and instead use
`minio`_. It's API compatible so it should reflect how AWS S3 works but
with the advantage that you don't need an Internet connection and real
S3 credentials just to test symbol uploads for example.

When started with docker, it starts a web server on ``:9000`` that you can
use to browse uploaded files. Go to ``http://localhost:9000``.

.. _`minio`: https://minio.io/


How to Memory Profile Python
============================

The trick is to install https://pypi.python.org/pypi/memory_profiler
(and ``psutil``) and then start Gunicorn with it. First start a
shell and install it there:

.. code-block:: shell

    $ docker-compose run --service-ports --user 0  web bash
    # pip install memory_profiler psutil

Now, to see memory reports of running functions, add some code to the
relevant functions you want to memory profile:

.. code-block:: python


    from memory_profiler import profile

    @profile
    def some_view(request):
        ...

Now run Gunicorn:

.. code-block:: shell

    $ python -m memory_profiler  `which gunicorn` tecken.wsgi:application -b 0.0.0.0:8000 --timeout 60 --workers 1 --access-logfile -


How to do local Upload by Download URL
======================================

When doing local development and you want to work on doing Symbol Upload
by HTTP posting the URL, you have a choice. Either put files somewhere
on a public network, or serve the locally.

Before we start doing local Upload By Download URL, you need to make your
instance less secure since you'll be using URLs like ``http://localhost:9090``.
Add ``DJANGO_ALLOW_UPLOAD_BY_ANY_DOMAIN=True`` to your ``.env`` file.

To serve them locally, first start the dev server (``make run``). Then
you need to start a bash shell in the current running web container:

.. code-block:: shell

    $ make currentshell

Now, you need some ``.zip`` files in the root of the project since it's
mounted and can be seen by the containers. Once they're there, start a
simple Python server:

.. code-block:: shell

    $ ls -lh *.zip
    $ python -m http.server --bind 0.0.0.0 9090

Now, you can send these in with ``tecken-loadtest`` like this:

.. code-block:: shell

    $ export AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxx
    $ python upload-symbol-zips.py http://localhost:8000 -t 160 --download-url=http://localhost:9090/symbols.zip

This way you'll have 3 terminals. 2 bash terminals inside the container
and one outside in the ``tecke-loadtests`` directory on your host.


Frontend linting - Prettier files
=================================

All ``.js`` files in the frontend code is expected to be formatted with
`Prettier`_. Ideally your editor should be configured to automatically
apply ``Prettier`` on save. Or by a git hook.

If you forget to format any files in a Pull Request, a linting check in
CircleCI will fail if any file hasn't been formatted. To test this locally,
use:

.. code-block:: shell

    $ docker-compose run frontend lint

If you get any output, it means it found files that should/could have been
formatted. The error message will explain what files need attention and
how to just format them all right now.

.. _`Prettier`: https://prettier.io/
