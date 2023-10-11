=============
Configuration
=============

.. contents::
   :local:

Symbols Service configuration
=============================

Gunicorn configuration:

.. everett:option:: GUNICORN_TIMEOUT
   :default: "300"

   Specifies the timeout value.

   https://docs.gunicorn.org/en/stable/settings.html#timeout

   Used in `bin/run_web.sh
   <https://github.com/mozilla-services/tecken/blob/main/bin/run_web.sh>`_.


.. everett:option:: GUNICORN_WORKERS
   :default: "1"

   Specifies the number of gunicorn workers.

   You should set it to ``(2 x $num_cores) + 1``.

   https://docs.gunicorn.org/en/stable/settings.html#workers

   http://docs.gunicorn.org/en/stable/design.html#how-many-workers

   Used in `bin/run_web.sh
   <https://github.com/mozilla-services/tecken/blob/main/bin/run_web.sh>`_.


Webapp configuration:

.. automoduleconfig:: tecken.settings._config
   :show-table:
   :hide-name:
   :case: upper
