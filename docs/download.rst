========
Download
========


History
=======

The original solution that Tecken replaces is `symbols.m.o`_ which was a
Heroku app that ran an Apache server that used proxy rewrites to
draw symbols from ``https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/``.

Its rewrite rules contained two legacy solutions:

1. `Uppercase the debug ID`_ in the filename.

2. Support having specific product names (e.g. ``firefox``) prefixing the
   name of the symbol file.


The old symbol download server was using ``symbols.mozilla.org`` and
was accessible only with ``http://``.

.. _`symbols.m.o`: https://github.com/mozilla-services/symbols.m.o
.. _`Uppercase the debug ID`: https://bugzilla.mozilla.org/show_bug.cgi?id=660932


What It Is
==========

Tecken Download's **primary use-case** is to redirect requests for symbols to
their ultimate source which is S3. For example, with a ``GET``, requesting
:base_url:`/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym`
will return a ``302 Found`` redirect to (at the time of writing)
``https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym``.

This way, all configuration of S3 buckets is central to Tecken even if we
decide to change to a different bucket or add/remove buckets.

The primary benefit of using Tecken Download instead of hitting S3 public
URLs directly is that it's just one URL to remember and Tecken Download
can iterate over a **list of S3 buckets**. This makes it possible to
upload symbols in multiple places but have them all accessible from one URL.

The other use-case of this is if you're simply curious to see if a symbol
file exists. Simply make a ``HEAD`` request instead of a ``GET``.

404s Logged
===========

All ``GET`` requests are logged and counted within Tecken. There is
a basic reporting option to extract ALL symbols that was requested
*yesterday* but couldn't be found. But note that the format is quite
particular since it doesn't report the third part of the URI. And
additionally it reports two extra possible query string parameters
called ``code_file`` and ``code_id``. So if you make a query like:
:base_url:`/foo.pdb/448794C699914DB8A8F9B9F88B98D7412/foo.sym?code_file=FOO.dll&code_id=BAR`
...yesterday, then request the CSV report at:
:base_url:`/missingsymbols.csv` it will contain a CSV line like this::

    foo.pdb,448794C699914DB8A8F9B9F88B98D7412,FOO.dll,BAR

The CSV report is actually ultimately to help the Socorro Processor
which used to manage reporting symbols that can't be found during
processing. See https://bugzilla.mozilla.org/show_bug.cgi?id=1361809


Ignore Patterns
===============

Certain files are repeatedly queried for by we know with confidence that
not only is it never in our symbol stores, it's also not worth logging
that it couldn't be found.

Right now, this is maintained as a configurable blacklist but is hard
coded inside the ``_ignore_symbol`` code in ``tecken.download.views``.

This approach might change over time as we're able to confidently
identify more and more patterns that we know we can ignore.


Download With Debug
===================

To know how long it took to make a "download", you can simply measure
the time it takes to send the request to Tecken for a specific symbol.
For example:

.. code-block:: shell

    $ time curl https://symbols.mozilla.org/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym

Note, that will tell you the total time it took your computer to make the
request to Tecken **plus** Tecken's time to talk to S3.

If you want to know how long it took Tecken *internally* to
talk to S3, you can add a header to your outgoing request. For example:

.. code-block:: shell

    $ curl -v -H 'Debug: true' https://symbols.mozilla.org/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym

Then you'll get a response header called ``Debug-Time``. In the ``curl``
output it will look something like this::

    < Debug-Time: 0.627500057220459

If that value is not present it's because Django was not even able to
route your request to the code that talks to S3. It can also come back
as exactly ``Debug-Time: 0.0`` which means the symbol is in a blacklist of
symbols that are immediately ``404 Not Found`` based on filename pattern
matching.
