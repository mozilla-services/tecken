========
Overview
========

.. contents::
   :local:


What is Tecken?
===============

Mozilla Symbol Server, codename "Tecken", is a web service for handling all
things symbols for Mozilla platform. In particular three major features:

1. Symbol Upload
2. Symbol Download
3. Symbolication


Architecture
============

Rough architecture diagram of Tecken:

.. image:: images/arch.png
   :alt: Tecken architecture diagram


.. Note::

   We're in the process of splitting out the symbolication API from the Tecken
   webapp into a separate microservice called Eliott.


Important services in the diagram:

* **Webapp:**

  Host: https://symbols.mozilla.org/

  The Tecken webapp handles upload, download, and symbolication.

  * **upload:** The webapp handles incoming uploads with the upload API. It
    manages upload permissions and bookkeeping of what was uploaded, by whom,
    and when. It exposes an interface for debugging symbol upload problems.

  * **download:** The webapp handles download API requests by finding the
    symbol file in one of the AWS S3 buckets and returning an HTTP redirect
    to the final location.

  * **symbolication:** The webapp has a symbolication API that handles
    converting module and memory offset information into symbols.

    .. Note::

       2021-08-30: The symbolication API is being rewritten as a separate microservice.

* **Eliot webapp (aka symbolication.mozilla.org):**

  Host: https://symbolication.mozilla.org/

  The Eliot webapp is a symbolication API microservice that uses the `Symbolic
  library <https://github.com/getsentry/symbolic>`_ to parse SYM files and do
  symbol lookups.

  Code is in the same repository as Tecken, but in the `eliot-service
  <https://github.com/mozilla-services/tecken/tree/main/eliot-service>`_
  subdirectory.

  .. Note::

     2021-08-30: This isn't in production, yet, so the url doesn't work.
