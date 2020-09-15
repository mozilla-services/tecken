.. _download:

========
Download
========

.. contents::
   :local:

Basics
======

Tecken handles requests for symbols files. Tecken takes the request, finds the
correct S3 bucket, and returns a redirect to that bucket. This allows us to use
multiple buckets for symbols without requiring everyone to maintain lists of
buckets.

For example, with a ``GET``, requesting
:base_url:`/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym` will
return a ``302 Found`` redirect to (at the time of writing)
``https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym``.


Missing symbols are logged
--------------------------

Tecken logs all requests for symbols files that don't exist in any of the
buckets.

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


File Extension Allow List
-------------------------

Tecken returns an HTTP 404 for symbols files requests where the extension
is not in the ``settings.DOWNLOAD_FILE_EXTENSIONS_ALLOWED`` list.


Debug Mode
==========

To know how long it took to make a "download", you can simply measure the time
it takes to send the request to Tecken for a specific symbol. For example:

.. code-block:: shell

    $ time curl --user-agent "example/1.0" \
        https://symbols.mozilla.org/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym

Note, that will tell you the total time it took your computer to make the
request to Tecken **plus** Tecken's time to talk to S3.

If you want to know how long it took Tecken *internally* to talk to S3, you can
add a header to your outgoing request. For example:

.. code-block:: shell

    $ curl --user-agent "example/1.0" -v -H 'Debug: true' \
        https://symbols.mozilla.org/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym

Then you'll get a response header called ``Debug-Time``. In the ``curl`` output
it will look something like this::

    < Debug-Time: 0.627500057220459

If that value is not present it's because Django was not even able to route
your request to the code that talks to S3. It can also come back as exactly
``Debug-Time: 0.0`` which means the symbol is in a block list of symbols that
are immediately ``404 Not Found`` based on filename pattern matching.


Refreshing the cache
====================

Tecken caches symbol file names and their final location aggressively. If you
need to bust the cache, you can append ``?_refresh`` to the url.

For example:

.. code-block:: shell

    $ curl --user-agent "example/1.0" https://symbols.mozilla.org/foo.pdb/HEX/foo.sym
    ...302 Found...

    # Now suppose you delete the file manually from S3 in the AWS Console.
    # And without any delay do the curl again:
    $ curl --user-agent "example/1.0" https://symbols.mozilla.org/foo.pdb/HEX/foo.sym
    ...302 Found...
    # Same old "broken", which is wrong.

    # Avoid it by adding ?_refresh
    $ curl --user-agent "example/1.0" https://symbols.mozilla.org/foo.pdb/HEX/foo.sym?_refresh
    ...404 Symbol Not Found...

    # Now our cache will be updated.
    $ curl --user-agent "example/1.0" https://symbols.mozilla.org/foo.pdb/HEX/foo.sym
    ...404 Symbol Not Found...


.. _download-try-builds:

Try Builds
==========

By default, when you request to download a symbol, Tecken will iterate through
a list of available S3 configurations.

To download symbols that might be part of a Try build you have to pass an
optional query string key ``try`` or you can prefix the URL with ``/try``.
For example:

.. code-block:: shell

    $ curl --user-agent "example/1.0" https://symbols.mozilla.org/tried.pdb/HEX/tried.sym?try
    ...302 Found...

    $ curl --user-agent "example/1.0" https://symbols.mozilla.org/try/tried.pdb/HEX/tried.sym
    ...302 Found...

If you specify that you're requesting a try build, Tecken will look at
all the S3 bucket locations as well as all the try locations in those
S3 buckets.

Symbols from Try builds is always tried last! So if there's a known symbol
called ``foo.pdb/HEX/foo.sym`` and someone triggers a Try build (which uploads
its symbols) with the exact same name (and build ID) and even if you use
``https://symbols.mozilla.org/foo.pdb/HEX/foo.sym?try`` the existing (non-Try
build) symbol will be matched first.


Downloading
===========

.. http:head:: /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Determine whether the symbol file exists or not.

   :reqheader Debug: if ``true``, includes debug output in the response

   :query try: use ``try=1`` to download Try symbols

   :query _refresh: use ``_refresh=1`` to force the cache to refresh

   :statuscode 200: symbol file exists
   :statuscode 404: symbol file does not exist
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 503: sleep for a bit and retry

.. http:get:: /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Download a symbol file.

   :reqheader Debug: if ``true``, includes debug output in the response

   :query try: use ``try=1`` to download Try symbols

   :query _refresh: use ``_refresh=1`` to force the cache to refresh

   :statuscode 302: symbol file was found and the final url was returned as a redirect
   :statuscode 400: requested symbol file has bad characters
   :statuscode 404: symbol file was not found
   :statuscode 429: sleep for a bit and retry
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 503: sleep for a bit and retry
