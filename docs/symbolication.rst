=============
Symbolication
=============


History
=======

The original implementation was Vladan Djeric's
`Snappy-Symbolication-Server`_ which was written in Tornado and was never
hosted with ops support or monitoring.

This is a re-write of that and baked in as one of multiple features in
Mozilla Symbol Server.

.. _`Snappy-Symbolication-Server`: https://github.com/vdjeric/Snappy-Symbolication-Server

What It Is
==========

You make a POST request to :base_url:`/symbolicate/v4` with a JSON body.
That JSON body has to contain certain keys and adhere to a specific format.
Here is an example:

.. code-block:: json

    {
      "memoryMap": [
        [
          "xul.pdb",
          "44E4EC8C2F41492B9369D6B9A059577C2"
        ],
        [
          "wntdll.pdb",
          "D74F79EB1F8D4A45ABCD2F476CCABACC2"
        ]
      ],
      "version": 4,
      "stacks": [
        [
          [0, 11723767],
          [1, 65802]
        ]
      ]
    }

The ``memoryMap`` is list of symbol filenames and their debug ID. Each 2-D
tuple corresponds to a path in our S3 symbol store. The full URL comes
from taking the base URL (e.g. ``https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/``)
plus the first first part (e.g. ``wntdll.pdb``) and then the debug ID
(e.g. ``D74F79EB1F8D4A45ABCD2F476CCABACC2``) and then lastly the first part
again but instead of ``.pdb`` it's replaced with ``.sym``.

So, as a full example, ``["wntdll.pdb", "D74F79EB1F8D4A45ABCD2F476CCABACC2"]``
becomes ``https://s3-us-west-2.amazonaws.com/org.mozilla.crash-stats.symbols-public/v1/wntdll.pdb/D74F79EB1F8D4A45ABCD2F476CCABACC2/wntdll.sym``.

The ``version`` key needs to be a 4. This might change in the future as the
symbolication server changes. For now, just set it to ``4``.

The ``stacks`` part is a list of lists, also known as "an array of stack traces".
Each stack trace is a list of "frames". Each frame is a 2-D tuple of
"module index" and "module offset". That module index is a number that corresponds
to an item in the ``memoryMap`` (see above). And the module offset is the
offset of this frame's instruction pointer relative to the base memory
address of the module in which the code is contained as an integer (in base 16).

So, in the example above, ``[1, 65802]`` means the 1th element (starting with 0)
in the ``memoryMap`` which in this example is
``["wntdll.pdb", "D74F79EB1F8D4A45ABCD2F476CCABACC2"]``.

What you get back is a JSON output that looks like this:

.. code-block:: json

    {
      "symbolicatedStacks": [
        [
          "XREMain::XRE_mainRun() (in xul.pdb)",
          "KiUserCallbackDispatcher (in wntdll.pdb)"
        ]
      ],
      "knownModules": [
        true,
        true
      ]
    }

The order of the ``symbolicatedStacks`` matches the order of the ``stacks``
sent in. Each item is a string of the format
``{function name} in ({module file name})``.

If the symbol can't find found a particular module, then the format becomes
``{module offset in hex} in ({module file name})``.

The ``knownModules`` list matches the order of the ``memoryMap`` list.
For each module and debug ID tuple, this is either ``True`` if the symbol file
could be found or ``False`` if it couldn't be found or couldn't be downloaded.

Note! ``knownModules`` makes no distinction if the symbol file failure to download is permanent
or temporary. The symbolication server attempts to retry failed downloads but
it uses caching to remember that it failed for a limited amount of time to
avoid hitting the same failure over and over.

The module offset (e.g. ``65802``) might not correspond to an exact location
in the module. If no exact location is found, it uses the nearest offset
rounded down.


How It Works
============

Each module index and module offset pair is iterated over in each stack.
The module index is used to load the symbol. Either from cache or from
the S3 source.

When it was not available in the cache and had to be downloaded, we parse
every line of the symbol file and extract all offsets and their function
names from the lines that start with either ``FUNC{space}`` or ``PUBLIC{space}``.
Only this mapping is saved in the cache.

Once the symbols have been loaded from that module, we try to look up
the offset. First we try to look up the exact offset and if that fails
we sort ALL offsets in that module and find the nearest one, rounded down.

If any of the offsets can't be converted to a hex, it gets skipped and
ignored. For example if you have a frame tuple that looks like this:
``[0, 1.00000]`` the resulting symbolication of that will simply be
``["1.00000"]`` as a string.


How Caching Works
=================

The S3 symbol storage is vastly bigger than the Symbol Server Symbolication
can have available at short notice so each symbol is looked up on the fly
and when looked up once, stored in a `Redis server`_ that is configured to work
to work as an LRU_ (Least Recently Used) cache.

It means it's capped and it will keep symbols that are frequently used hot.
When the Redis LRU cache saves an entry, it compares if the total memory used
is now going to be bigger than the maximum memory amount
(configured by config or by  the limit of the server it runs on) allowed.
If so, it figures out which keys were **least recently** used and deletes
them from Redis. The default configuration for how many it deletes is 5 but
you can change that in configuration.

The eviction policy of the Redis LRU is ``allkeys-lru``. If the eviction
policy is not changed to one that evicts, every write would cause an error
when you try to save new symbols.

.. _LRU: https://en.wikipedia.org/wiki/Cache_replacement_policies#Least_Recently_Used_.28LRU.29
.. _`Redis server`: https://redis.io/topics/lru-cache


Symbolication With Debug
========================

The expected input JSON is listed above. If you add an extra key ``debug``
with a trueish value, the output will contain an additional ``debug`` key.
For example, the output might look like this:

.. code-block:: json


    {
      "debug": true,
      "memoryMap": [
        [
          "xul.pdb",
          "44E4EC8C2F41492B9369D6B9A059577C2"
        ],
        [
          "wntdll.pdb",
          "D74F79EB1F8D4A45ABCD2F476CCABACC2"
        ]
      ],
      "version": 4,
      "stacks": [
        [
          [0, 11723767],
          [1, 65802]
        ]
      ]
    }

This will return an output that can look like this:

.. code-block:: json

    {
        "debug": {
            "cache_lookups": {
                "count": 2,
                "size": 0,
                "time": 0.006340742111206055
            },
            "downloads": {
                "count": 2,
                "size": 70490521,
                "time": 16.34278154373169
            },
            "modules": {
                "count": 2,
                "stacks_per_module": {
                    "wntdll.pdb/D74F79EB1F8D4A45ABCD2F476CCABACC2": 1,
                    "xul.pdb/44E4EC8C2F41492B9369D6B9A059577C2": 1
                }
            },
            "stacks": {
                "count": 2,
                "real": 2
            },
            "time": 16.75939154624939
        },
        "knownModules": [
            true,
            true
        ],
        "symbolicatedStacks": [
            [
                "XREMain::XRE_mainRun() (in xul.pdb)",
                "KiUserCallbackDispatcher (in wntdll.pdb)"
            ]
        ]
    }

The keys inside the ``debug`` block means as follows:

* ``cache_lookups.count`` - how many times it tried to do a query on
  the LRU cache

* ``cache_lookups.size`` - the total bytes size of data returned by the
  LRU cache

* ``cache_lookups.time`` - total time it took to make these queries on the
  LRU cache

* ``downloads.count`` - number of successful downloads of symbols over
  the network

* ``downloads.size`` - the total bytes size of symbols downloaded
  when uncompressed

* ``downloads.time`` - total time it took to make these downloads over
  the network

* ``modules.count`` - number of modules that needed to be looked up

* ``modules.stacks_per_module`` - number of stacks that were referring to
  each module

* ``stacks.count`` - total number of frames in all stack traces that were
  symbolicated

* ``stacks.real`` - total number of frames in all stack traces that were
  symbolicated except those offsets that couldn't be converted to hex.


URL shortcut
============

The ideal URL to POST request to is :base_url:`/symbolicate/v4`
but to support legacy usage when the domain was `symbolapi.mozilla.org`
you can also do the same POST request to :base_url:`/` too.


Example Symbolication
=====================

Here's an example you can copy and paste::

    curl -d '{"stacks":[[[0,11723767],[1, 65802]]],"memoryMap":[["xul.pdb","44E4EC8C2F41492B9369D6B9A059577C2"],["wntdll.pdb","D74F79EB1F8D4A45ABCD2F476CCABACC2"]],"version":4}' http://localhost:8000


Sporadic Network Errors
=======================

If you try to run a symbolication on a flaky network all sorts of network
errors can happen between the symbolication service and the general
symbol store (S3). If any of these errors occur, it does **not** break
the request but in the symbolication output, the module is simply marked
as not known.

The list of errors that might occur are:

* ``requests.exceptions.ConnectionError`` (e.g. DNS errors)

* ``requests.exceptions.SSLError`` (happens if the network connection breaks
  whilst TLS handshaking)

* ``requests.exceptions.ReadTimeout`` (unlikely but can happen either
  network is temporarily saturated)

* ``requests.exceptions.ContentDecodingError`` (if a symbol is served in a
  non-gzip way and can't be decompressed)
