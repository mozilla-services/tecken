======================
Docker Tips and Tricks
======================

Docker is used to do development and continuous integration on ``tecken``.
Below is a list of miscellaneous techniques to make development easier.

Bashing whilst running
======================

If you have two terminals open, and run ``make run`` in one and ``make bash``
in another they are entirely separate containers. Meaning, if you, in the
second terminal where you started bash try editing a file like this:

.. code-block:: shell

    > jed /usr/local/lib/python3.5/site-packages/django/http/request.py

Any changes are ignored by the first container. The solution is to run this
command:

.. code-block:: shell

    $ docker-compose exec --user 0 web bash

When you run that, you'll first notice that it opens almost instantly
since there's no booting-up time. Also, if you, in a *third* terminal
now run ``docker-compose ps`` you'll see that there is no new container
started. Now, any changes you make to files in this bash gets used by
the Django runserver in the first terminal.

All the changes you make (e.g. print statements inside some Python
<<<<<<< HEAD
dependency) is wiped any and forgotten when you stop the first container.
=======
dependency) is wiped any and forgotten when you rebuild the containers.
>>>>>>> 2b8447dde08cdf15bd31d5c665be80b0ff06f8c8

This is aliased in the ``Makefile`` as ``make currentshell``.

Running from bash
=================

When you run ``docker-compose up`` it automatically takes care of exposing
the port instructions mentioned in ``docker-compose.yml``. That means
when you run ``docker-compose up web`` you'll be able to reach port ``8000``
inside the container from *outside* the container. However, if you for some
reason want to go into the shell, do some magic, and then start Django's
runserver from within, it won't be reachable unless you start the shell
in this way:

.. code-block:: shell

   $ docker-compose run --service-ports -u 0 web bash

Note the extra ``--service-ports``.


What's Booted?
==============

The ``docker ps`` list will all containers that are running. But
``docker-compose ps`` will list the same containers but with different
information. The former gives nice stats on up when it was created and
how long it's been up. The latter will give information about containers
also have have been stopped.
