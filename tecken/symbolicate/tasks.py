# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

from celery import shared_task

from tecken.symbolicate.utils import invalidate_symbolicate_cache


@shared_task
def invalidate_symbolicate_cache_task(symbol_keys):
    invalidate_symbolicate_cache(symbol_keys)
