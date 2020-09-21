.. _download:

========
Download
========

.. contents::
   :local:

Basics
======

Tecken handles requests for symbols files. Tecken takes the request, figures
out which bucket the file is in, and returns a redirect to that bucket. This
allows us to use multiple buckets for symbols without requiring everyone to
maintain lists of buckets.

For example, at the time of this writing doing a ``GET`` for
:base_url:`/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym` will
return a ``302 Found`` redirect to
``https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/firefox.pdb/448794C699914DB8A8F9B9F88B98D7412/firefox.sym``.

In addition to finding symbols files and returning redirects, Tecken keeps
track of which files ending with ``.pdb`` and ``.sym`` that it couldn't find.
These are known as "missing symbols".


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


Downloading API
===============

.. http:head:: /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Determine whether the symbol file exists or not.

   :reqheader Debug: if ``true``, includes a ``Debug-Time`` header in the response.

      If ``Debug-Time`` is `0.0``: symbol file ends in an unsupported extension

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :query try: use ``try=1`` to download Try symbols

   :query _refresh: use ``_refresh=1`` to force Tecken to look for the symbol file
       in the AWS S3 buckets and update the cache

   :statuscode 200: symbol file exists
   :statuscode 404: symbol file does not exist
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 503: sleep for a bit and retry

.. http:get:: /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Download a symbol file.

   :reqheader Debug: if ``true``, includes a ``Debug-Time`` header in the response.

      If ``Debug-Time`` is `0.0``: symbol file ends in an unsupported extension

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :query try: use ``try=1`` to download Try symbols

   :query _refresh: use ``_refresh=1`` to force Tecken to look for the symbol file
       in the AWS S3 buckets and update the cache

   :statuscode 302: symbol file was found and the final url was returned as a redirect
   :statuscode 400: requested symbol file has bad characters
   :statuscode 404: symbol file was not found
   :statuscode 429: sleep for a bit and retry
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 503: sleep for a bit and retry

.. http:head:: /try/<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Same as ``HEAD /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>``, but for try symbols.

.. http:get:: /try/<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>

   Same as ``GET /<DEBUG_FILENAME>/<DEBUG_ID>/<SYMBOL_FILE>``, but for try symbols.


Missing symbols APIs
====================

.. http:get:: /missingsymbols.csv

   Download missing symbol information as a CSV.

   Format::

      debug_file,debug_id,code_file,code_id

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :statuscode 200: ok
   :statuscode 429: sleep for a bit and retry
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 503: sleep for a bit and retry


.. http:get:: /missingsymbols/

   Download missing symbol information.

   For example:

   .. code-block:: shell

      curl --user-agent "example/1.0" \
         'https://symbols.mozilla.org/missingsymbols/?filename=libxul'

   :reqheader User-Agent: please provide a unique user agent to make it easier for us
       to help you debug problems

   :query symbol: (optional) the symbol to filter on by substring match
   :query debugid: (optional) the debugid to filter on by substring match
   :query filename: (optional) the filename to filter on by substring match
   :query code_file: (optional) the code_file to filter on by substring match
   :query code_id: (optional) the code_id to filter on by substring match
   :query modified_at: (optional) comma-separated date filters for modified_at timestamp

       Valid comparisons: ``<=``, ``>=``, ``=``, ``<``, ``>``

       Example: ``modified_at=>=2020-09-01,<2020-09-02``
       (url-encoded ``modified_at=%3E%3D=2020-09-01%2C%3C2020-09-02``)

   :query created_at: (optional) comma-separated date filters for created_at timestamp

       Valid comparisons: ``<=``, ``>=``, ``=``, ``<``, ``>``

       Example: ``created_at=>=2020-09-01,<2020-09-02``
       (url-encoded ``created_at=%3E%3D=2020-09-01%2C%3C2020-09-02``)

   :query sort: (optional) the field to sort by; defaults to ``modified_at``
   :query reverse: (optional) if you want the sort reversed; defaults to
       ``false``

   :resheader Content-Type: application/json

   :>json obj order_by: sort specification

       :sort (str): the sort field
       :reverse (bool): whether or not it's reversed

   :>json int batch_size: the number of records in a page
   :>json int page: the page being returned
   :>json int total_count: the total number of records in the query

   :>json array records: the list of records where each record consists of

       :id (int): the record id
       :symbol (str): the debug symbol
       :debugid (str): the debug id
       :filename (str): the filename
       :code_file (str): the code_file or null
       :code_id (str): the code_id or null
       :count (int): how many times this symbol file was requested
       :modified_at (timestamp): the last time this symbol file was requested;
           iso8601 in UTC; YYYY-MM-DDThh:mm:ss.sssZ
       :created_at (timestamp): the first time this symbol file was requested;
           iso8601 in UTC; YYYY-MM-DDThh:mm:ss.sssZ

   :statuscode 200: ok
   :statuscode 400: request was invalid; fix and retry
   :statuscode 429: sleep for a bit and retry
   :statuscode 500: sleep for a bit and retry; if retrying doesn't work, then please
       file a bug report
   :statuscode 503: sleep for a bit and retry
