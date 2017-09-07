============
Benchmarking
============

Motivation
==========

This documentation is about the benchmarking that is explicit. I.e. code that
is written purely for the benefit of running benchmarks. You can of course
do your own benchmarking of the "real functionality" your own way but we
have built-in benchmarking code that is ideal for stress testing certain
contained features.

Configuration
=============

The most important configuration is to **enable or disable *all* benchmarking**.
To do this set the ``DJANGO_BENCHMARKING_ENABLED`` environment variable.

By default all benchmarking is disabled. That's because we don't want to risk
a bad benchmark that could disrupt production systems. It's best to enable,
per environment, one at a time explicitly and disable benchmarking again
when no more testing is necessary.

Then ``DJANGO_BENCHMARKING_ENABLED`` is ignored if the current user hitting
the benchmark URL is a superuser.

Usage
=====

The best approach is to read the source code to find out what benchmarks
are available and what kind of options they accept or require.

To do that look at the code of ``tecken/benchmarking/urls.py`` and
``tecken/benchmarking/views.py``

But basically the idea is that every benchmark is started by querying a
