# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

import logging

import markus

from tecken.download.models import MissingSymbol


logger = logging.getLogger("tecken")
metrics = markus.get_metrics("tecken")


@metrics.timer_decorator("download_store_missing_symbol")
def store_missing_symbol(symbol, debugid, filename, code_file=None, code_id=None):
    # Ignore it if it's clearly some junk or too weird.
    if len(symbol) > 150:
        logger.info(f"Ignoring log missing symbol (symbol ${len(symbol)} chars)")
        return
    if len(debugid) > 150:
        logger.info(f"Ignoring log missing symbol (debugid ${len(debugid)} chars)")
        return
    if len(filename) > 150:
        logger.info(f"Ignoring log missing symbol (filename ${len(filename)} chars)")
        return
    if code_file and len(code_file) > 150:
        logger.info(f"Ignoring log missing symbol (code_file ${len(code_file)} chars)")
        return
    if code_id and len(code_id) > 150:
        logger.info(f"Ignoring log missing symbol (code_file ${len(code_id)} chars)")
        return
    hash_ = MissingSymbol.make_md5_hash(symbol, debugid, filename, code_file, code_id)
    for missing_symbol in MissingSymbol.objects.raw(
        """
            INSERT INTO download_missingsymbol (
                hash, symbol, debugid, filename, code_file, code_id,
                count, created_at, modified_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                1, CLOCK_TIMESTAMP(), CLOCK_TIMESTAMP()
              )
            ON CONFLICT (hash)
            DO UPDATE SET
                count = download_missingsymbol.count + 1,
                modified_at = CLOCK_TIMESTAMP()
            WHERE download_missingsymbol.hash = %s
            RETURNING id, created_at, modified_at
            """,
        (hash_, symbol, debugid, filename, code_file or None, code_id or None, hash_),
    ):
        # You can now use the created_at and modified_at to see if it caused an
        # update or a creation.
        # Because there is a miniscule delay, in PostgreSQL, between calling
        # CLOCK_TIMESTAMP() one time and CLOCK_TIMESTAMP() immediately after,
        # we can't compare the dates after the upsert.
        equal = (
            missing_symbol.modified_at - missing_symbol.created_at
        ).total_seconds() < 0.0001
        if equal:
            # it was an insert!
            MissingSymbol.incr_total_count()

    return hash_
