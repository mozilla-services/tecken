========
Glossary
========

.. glossary::
   :sorted:

   dump_syms
       dump_syms is a tool for parsing the debugging information the compiler
       provides (whether as DWARF or STABS sections in an ELF file or as
       stand-alone PDB files) and writing that information back out in the
       Breakpad symbol file format.

       .. seealso::

          `dump_syms <https://github.com/mozilla/dump_syms>`__
              dump_syms project.


   symbols
   symbols file
       When compiling a build, the compiler generates binaries with debugging
       symbols in them.

       The build system uses :term:`dump_syms` to extract the debugging symbols
       from the binaries and put them in Breakpad-style symbol files.

       An entry in the symbol file is something like "This set of bytes in this
       binary correspond to function JammyJamJam on line 200 in source file
       jampocalypso.c."

       Let's create a symbol file.

       We can create a new Rust project, build it, then extract symbols from
       it using :term:`dump_syms`::

           $ cargo new testproj
           $ cd testproj
           $ cargo build
           $ dump_syms target/debug/testproj > testproj.sym

       That creates a sym file like this::

           MODULE Linux x86_64 D48F191186D67E69DF025AD71FB91E1F0 testproj
           ...
           FILE 5 /home/willkg/projects/testproj/src/main.rs
           ...
           FUNC 5380 44 0 testproj::main
           5380 9 1 5
           5389 36 2 5
           53bf 5 3 5

       This sym file is 6,809 lines for a "Hello, world!" binary.

       .. seealso::

          `Breakpad symbol format <https://chromium.googlesource.com/breakpad/breakpad/+/HEAD/docs/symbol_files.md>`__
              Specification for Breakpad symbol file format.


   symbolication
       Symbolication is the act of converting an array of addresses and module
       information into symbols of the function in the source code for that
       address.

       Here's an array of modules loaded in memory and a stack defined as an
       array of memory offsets::

           {"jobs": [{
             "memoryMap": [
               [ "firefox.pdb", "5F84ACF1D63667F44C4C44205044422E1" ],
               [ "mozavcodec.pdb", "9A8AF7836EE6141F4C4C44205044422E1" ],
               [ "Windows.Media.pdb", "01B7C51B62E95FD9C8CD73A45B4446C71" ],
               [ "xul.pdb", "09F9D7ECF31F60E34C4C44205044422E1" ],
               // ...
             ],
             "stacks": [[
               [ 3, 6516407 ],
               [ 3, 12856365 ],
               [ 3, 12899916 ],
               [ 3, 13034426 ],
               [ 3, 13581214 ],
               [ 3, 13646510 ],
               // ...
             ]]
           }]}

       We can use the sym files, look up the memory addresses, and find the
       symbols for them. That gets us this::

           0  xul.pdb  mozilla::ConsoleReportCollector::FlushReportsToConsole(unsigned long long, nsIConsoleReportCollector::ReportAction)
           1  xul.pdb  mozilla::net::HttpBaseChannel::MaybeFlushConsoleReports()",
           2  xul.pdb  mozilla::net::HttpChannelChild::OnStopRequest(nsresult const&, mozilla::net::ResourceTimingStructArgs const&, mozilla::net::nsHttpHeaderArray const&, nsTArray<mozilla::net::ConsoleReportCollected> const&)
           3  xul.pdb  std::_Func_impl_no_alloc<`lambda at /builds/worker/checkouts/gecko/netwerk/protocol/http/HttpChannelChild.cpp:1001:11',void>::_Do_call()
          ...

       That's symbolication.

       .. seealso::

          `Mozilla Symbolication Server <https://symbolication.services.mozilla.com/>`__

          `Eliot <https://mozilla-eliot.readthedocs.io/>`__
              Documentation for the Mozilla Symbolication Server.
