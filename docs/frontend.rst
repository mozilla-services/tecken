======================
Frontend Documentation
======================

Overview
========

The frontend code tries to be as separate from the web server code as possible.
The frontend is a static app (written in React with ``react-router``) that
communicates with the web server by making AJAX calls for JSON/REST and
rendering in run-time.

The goal is for the web server (i.e. Django) to only return pure
responses in JSON (or plain text or specific to some files) and never
generate HTML templates.

The Code
========

All source code is in the ``./frontend`` directory. More specifically
the ``./frontend/src`` which are the files you're most likely going to
edit to change the front-end.

All ``CSS`` is loaded with ``yarn`` by either drawing from ``.css`` files
installed in the ``node_modules`` directory or from imported ``.css`` files
inside the ``./frontend/src`` directory.

The project is based on `create-react-app`_ so the main rendering engine
is React. There is no server-side rendering. The idea is that all (unless
explicitly routed in Nginx) requests that don't immediately find a static file
should fall back on ``./frontend/build/index.html``. For example, loading
:base_url:`/uploads/browse` will actually load ``./frontend/build/index.html``
which renders the ``.js`` bundle which loads ``react-router`` which, in turn,
figures out which component to render and display based on the path
("/uploads/browse" for example).

.. _`create-react-app`: https://github.com/facebookincubator/create-react-app


Upgrading/Adding Dependencies
=============================

A "primitive" way of changing dependencies is to edit the list
of dependencies in ``frontend/package.json`` and running
``docker-compose build frontend``. **This is not recommended**.

A much better way to change dependencies is to use ``yarn``. Use
the ``yarn`` installed in the Docker frontend container. For example:

.. code-block:: shell

    $ docker run -it tecken_frontend bash
    > yarn outdated           # will display which packages can be upgraded today
    > yarn upgrade date-fns   # example of upgrading an existing package
    > yarn add new-hotness    # adds a new package

When you're done, you have to rebuild the frontend Docker container:

.. code-block:: shell

    $ docker-compose build frontend

Your change should result in changes to ``frontend/package.json`` *and*
``frontend/yarn.lock`` which needs to both be checked in and committed.


Production Build
================

(At the moment...)

Ultimately, the command ``cd frontend && yarn run build`` will output
all the files you need in the ``build`` directory. These files are purely
static and do *not* depend on NodeJS to run in production.

The contents of the directory changes names every time and ``.css`` and
``.js`` files are not only minified and bundled, they also have a hash
in the filename so the files can be very aggressively cached.

The command to generate the build artifact is done by CircleCI.
See the ``circle.yml`` file which kicks off a build.

You never need the production build when doing local development, on your
laptop, with Docker.

Dev Server
==========

For local development, when you run ``docker-compose up web worker frontend``
it starts the NodeJS dev server in the foreground, mixing its output with
that of Django and Celery. Normally in ``create-react-app`` apps, the
``yarn start`` command is highly interactive, clears the screen, runs in
full screen in the terminal, color coded and able to spit out any
warnings or compilation errors. When run in docker, with non-TTY terminal,
all output from the dev server is sent to ``stdout`` one line at a time.

When you start Docker for development (again ``make run`` or
``docker-compose up web worker frontend``) it starts the dev server on port
``:3000`` and it also exposes a WebSocket on port ``:35729``.

The WebSocket is there to notice if you change any of the source files, it then
triggers a "hot reload" which tells the browser to reload
``http://localhost:3000``.

Proxying
========

The dev server is able to proxy any requests that would otherwise be a
``404 Not Found`` over to the the same URL but with a different host.
See the ``frontend/package.json`` (the "proxy" section). Instead, it
rewrites the request to ``http://web:8000/$uri`` which is the Django server.
So, if in ``http://localhost:3000`` you try to load something like
``http://localhost:3000/api/users/search`` it knows to actually forward
that to ``http://localhost:8000/api/users/search``.

When you run in production, this is entirely disabled. To route requests
between the Django server and the static files (with its ``react-router``
implementation) that has to be configured in Nginx.

Authentication and Auth0
========================

The frontend app does **not** handle authentication. Instead it relies on the
browser to be able to maintain a cookie from the web server in consequent
AJAX requests. This is done by doing fetches with "same-origin" credentials;
meaning the frontend trusts that the client will pass its current cookies
when it makes the AJAX request if and only if the origin is the same.

There is a REST endpoint the frontend talks to under ``/api/auth`` which
will tell the frontend if the client has a valid cookie, and/or the URL
needed to go to to make the client authenticate herself with Auth0 and the
Django web server.

No credentials are ever passed between the frontend and the Django web server.
Only the user's email. This presence helps the frontend decide whether to
render the "Sign In" or the "Sign Out" button.

Django API Endpoints
====================

All AJAX requests from the frontend to the Django server should go via the
``/api/`` prefix which is the ``tecken.api`` Django app. This Django
app will be for all frontend apps such as user management, API tokens or
browsing the uploads history.


Watch out for ``node_modules``!
===============================

If you ever run and build the frontend outside of Docker you end up with
a directory ``frontend/node_modules`` which is ignored by git but is still
part of the current working directory that Docker serves up and will
cause things like ``make build`` be excessively slow since the directory
can end up north of 100MB.

If you have a ``frontend/node_modules`` directory, feel free to delete it.

The dev server runs in a separate Docker container which builds its
``node_modules`` outside the files mounted to the host.

Working on ``Docerfile.frontend``
=================================

If you make changes to ``Dockerfile.frontend`` you have to rebuild that
container. A trick, to avoid having to rebuild everything is to just run:

.. code-block:: shell

    docker-compose build frontend

Testing
=======

There are no unit, integration or functional tests of the frontend.

A nice-to-have but considering the current expected amount of traffic/users
it's not worth the effort.


State Management in React
=========================

The frontend app uses ``react-router`` to render different React components
depending on the ``pushState`` URL. If a piece of state is needed, and it's
contained to one component, use regular ``this.setState()``. If a piece of
state is needed across all (or most) components add it to the ``Mobx`` store.
See the file ``frontend/src/Store.js``. Changes to that object will
trigger re-render of all active components that are observing the store.
