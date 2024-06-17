# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from concurrent.futures import Executor, Future, ThreadPoolExecutor
from typing import Callable, Optional, TypeVar

from encore.concurrent.futures.synchronous import SynchronousExecutor


# A global thread pool executor used for parallel file uploads.
EXECUTOR: Optional[Executor] = None


def init(synchronous: bool, max_workers: int):
    """Initialize the executor."""
    global EXECUTOR
    if synchronous:
        # This is only applicable when running unit tests
        EXECUTOR = SynchronousExecutor()
    else:
        EXECUTOR = ThreadPoolExecutor(max_workers=max_workers)


T = TypeVar("T")


def submit(fn: Callable[..., T], /, *args, **kwargs) -> Future[T]:
    """Submit a job to the executor."""
    return EXECUTOR.submit(fn, *args, **kwargs)
