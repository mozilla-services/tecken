.. _download:

========
Download
========

Downloading basics
==================

Tecken download's redirects incoming requests for symbols to their final
location. This allows Tecken to manage multiple S3 buckets without requiring
anyone to maintain lists of locations.

For example, with a ``GET``, requesting
:base_url:`/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym` will
return a ``302 Found`` redirect to (at the time of writing)
``https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym``.


Missing symbols are logged
==========================

Tecken logs all ``GET`` requests for symbols files that don't exist.

You can access a CSV report at :base_url:`/missingsymbols.csv` of this data.

For example, if a ``GET`` is for
:base_url:`/foo.pdb/448794C699914DB8A8F9B9F88B98D7412/foo.sym?code_file=FOO.dll&code_id=BAR`
then the CSV will include something like this::

    debug_file,debug_id,code_file,code_id
    foo.pdb,448794C699914DB8A8F9B9F88B98D7412,FOO.dll,BAR

This CSV report is used to find missing symbols and upload them to Tecken.
This improves crash report processing in Socorro.

Tecken only yields missing symbols whose symbol ended with ``.pdb`` and filename
ended with ``.sym`` (case insensitively).


Ignore Patterns
===============

We know with confidence users repeatedly query certain files that are never in
our symbol stores. We can ignore them to suppress logging that they couldn't be
found.

Right now, this is maintained as a configurable block list but is hard coded
inside the ``_ignore_symbol`` code in ``tecken.download.views``.

This approach might change over time as we're able to confidently identify more
and more patterns that we know we can ignore.


File Extension Allow List
=========================

When someone requests to download a symbol, as mentioned above, we have some
ways to immediately decide that it's a 404 Symbol Not Found without even
bothering to ask the cache or S3.

As part of that, there is also a list of allowed file extensions that are the
only ones we should bother with. This list is maintained in
``settings.DOWNLOAD_FILE_EXTENSIONS_ALLOWED`` (managed by the environment
variable ``DJANGO_DOWNLOAD_FILE_EXTENSIONS_ALLOWED``) and this list is found in
the source code (``settings.py``) and also visible on the home page if you're
signed in as a superuser.


Download With Debug
===================

To know how long it took to make a "download", you can simply measure the time
it takes to send the request to Tecken for a specific symbol.  For example:

.. code-block:: shell

    $ time curl https://symbols.mozilla.org/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym

Note, that will tell you the total time it took your computer to make the
request to Tecken **plus** Tecken's time to talk to S3.

If you want to know how long it took Tecken *internally* to talk to S3, you can
add a header to your outgoing request. For example:

.. code-block:: shell

    $ curl -v -H 'Debug: true' \
        https://symbols.mozilla.org/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym

Then you'll get a response header called ``Debug-Time``. In the ``curl`` output
it will look something like this::

    < Debug-Time: 0.627500057220459

If that value is not present it's because Django was not even able to route
your request to the code that talks to S3. It can also come back as exactly
``Debug-Time: 0.0`` which means the symbol is in a block list of symbols that
are immediately ``404 Not Found`` based on filename pattern matching.


Download Without Caching
========================

Generally we can cache our work around S3 downloads quite aggressively since we
tightly control the (only) input. Whenever a symbol archive file is uploaded,
for every file within that we upload to S3 we also invalidate it from our
cache. That means we can cache information about whether certain symbols exist
in S3 or not quite long.

However, if you are debugging something or if you manually remove a symbol from
S3 that control is "lost". But there is a way to force the cache to be ignored.
However, it only ignores looking in the cache. It will always update the cache.

To do this append ``?_refresh`` to the URL. For example:

.. code-block:: shell

    $ curl https://symbols.mozilla.org/foo.pdb/HEX/foo.sym
    ...302 Found...

    # Now suppose you delete the file manually from S3 in the AWS Console.
    # And without any delay do the curl again:
    $ curl https://symbols.mozilla.org/foo.pdb/HEX/foo.sym
    ...302 Found...
    # Same old "broken", which is wrong.

    # Avoid it by adding ?_refresh
    $ curl https://symbols.mozilla.org/foo.pdb/HEX/foo.sym?_refresh
    ...404 Symbol Not Found...

    # Now our cache will be updated.
    $ curl https://symbols.mozilla.org/foo.pdb/HEX/foo.sym
    ...404 Symbol Not Found...


.. _download-try-builds:

Try Builds
==========

By default, when you request to download a symbol, Tecken will iterate through
a list of available S3 configurations.

To download symbols that might be part of a Try build you have to pass an
optional query string key: ``try``. Or you can prefix the URL with ``/try``.
For example:

.. code-block:: shell

    $ curl https://symbols.mozilla.org/tried.pdb/HEX/tried.sym
    ...404 Symbol Not Found...

    $ curl https://symbols.mozilla.org/tried.pdb/HEX/tried.sym?try
    ...302 Found...

    $ curl https://symbols.mozilla.org/try/tried.pdb/HEX/tried.sym
    ...302 Found...

What Tecken does is, if you pass ``?try`` to the URL or use the ``/try``
prefix, it takes the existing list of S3 configurations and *appends* the S3
configuration for Try builds.

Note: symbols from Try builds is always tried last! So if there's a known
symbol called ``foo.pdb/HEX/foo.sym`` and someone triggers a Try build (which
uploads its symbols) with the exact same name (and build ID) and even if you
use ``https://symbols.mozilla.org/foo.pdb/HEX/foo.sym?try`` the existing
(non-Try build) symbol will be matched first.
