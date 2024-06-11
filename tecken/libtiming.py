# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from contextlib import contextmanager
import time
from typing import Callable, TypeVar


T = TypeVar("T")


def measure_time(func: Callable[..., T], *args, **kwargs) -> tuple[T, float]:
    """Run the function, returning both the return value and the elapsed wall time."""
    start_time = time.perf_counter()
    return_value = func(*args, **kwargs)
    elapsed_time = time.perf_counter() - start_time
    return return_value, elapsed_time


@contextmanager
def record_timing(msg, stdout):
    """Context manager for timing code and writing it to a writer

    :arg msg: the message to write with the output
    :arg stdout: the stdout file-like thing to write to

    """
    start_time = time.perf_counter()

    yield

    end_time = time.perf_counter()
    delta = end_time - start_time
    stdout.write(f"Elapsed: {msg}: {delta:.2f}s")
