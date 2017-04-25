========
Download
========


History
=======

The original solution that ``tecken`` replaces is `symbols.m.o`_ which was a
Heroku app that ran an Apache server that used proxy rewrites to
draw symbols from ``https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/``.

Its rewrite rules contained two legacy solutions:

1. `Uppercase the debug ID`_ in the filename.

2. Support having specific product names (e.g. ``firefox``) prefixing the
   name of the symbol file.


The old symbol download server was using ``symbols.mozilla.org`` and
was accessible only with ``http://``.

.. _`symbols.m.o`: https://github.com/mozilla/symbols.m.o
.. _`Uppercase the debug ID`: https://bugzilla.mozilla.org/show_bug.cgi?id=660932


What It Is
==========

A proxy for S3. All symbols are stored in S3. ``tecken` just makes those files
available. It acts as a proxy, so when you request, for example,
:base_url:`/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym`
from ``tecken`` it goes and tries to download that from the configured
list of S3 buckets that it knows about. If not found in S3, that
``404 Not Found`` is propagated through.

Ultimately, if you know where the symbols are hosted directly on S3,
it's technically faster to download directly from that. But since
``tecken`` is hosted in AWS, the slow-down of proxying is miniscule.

Plus ``tecken`` has the potential to do much more advanced S3 lookups.
For example, it can, based on input parameters or authorization parameters
look up from specific buckets that are not default.

``HEAD`` or ``GET`` only
========================

The only protocols supported are ``HEAD`` and ``GET``.

At the time of writing, ``ETag`` and ``If-Modified-Since`` are not supported.
