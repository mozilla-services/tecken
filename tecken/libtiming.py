# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from contextlib import contextmanager
import timeit


@contextmanager
def record_timing(msg, stdout):
    """Context manager for timing code and writing it to a writer

    :arg msg: the message to write with the output
    :arg stdout: the stdout file-like thing to write to

    """
    start_time = timeit.default_timer()

    yield

    end_time = timeit.default_timer()
    delta = end_time - start_time
    stdout.write(f"Elapsed: {msg}: {delta:.2f}s")
