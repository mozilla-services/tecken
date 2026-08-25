# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import codecs
import logging
import threading
import zlib

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction
from django.db.models import Case, F, When
import requests

from tecken.librequests import session_with_retries
from tecken.libstorage import Notification, queue_from_config
from tecken.libsym import SymParseError, extract_sym_header_data
from tecken.upload.models import FileUpload, Upload
from tecken.upload.utils import is_sym_file, should_compressed_key

logger = logging.getLogger("tecken")


class Command(BaseCommand):
    help = "Run the worker process that records finished uploads in the database."

    def handle(self, *args, **options):
        run_finalization_worker()


def run_finalization_worker(stop_event: threading.Event | None = None):
    """Consume finalization notifications until the optional stop event is set."""
    logger.info("Finalization worker starting...")
    queue = queue_from_config(settings.PUBSUB_QUEUE)
    queue.subscribe(process_notification, stop_event=stop_event)


def process_notification(notification: Notification):
    # When processing HTTP requests, Django automatically cleans up obsolete connections both
    # before and after each request, using its `request_started` and `request_finished` signals.
    # Pub/sub notifications are processed in worker threads, but they don't pass through any
    # Django middleware, so we need to take care of closing old connections ourselves. Closing
    # connections after processing is required for the tests, but also mirrors Django's behaviour
    # for HTTP requests.
    close_old_connections()
    try:
        _process_notification(notification)
    finally:
        close_old_connections()


def _process_notification(notification: Notification):
    """Process an ojbect finalization notification.

    This function recevies notifications about fully uploaded objects and records information
    about them in the database. Since pub/sub messages can be received multiple times, the
    processing in this function must be idempotent.

    If this function throws an error, the pub/sub messgae won't be acked. This means the message
    will be resent, and this function will be called again with the same data. This means we
    should catch and swallow any error that's expected to be permanent, and only potentially
    temporary errors, e.g. problems connecting to the database, should ever be thrown. It only
    makes sende to process a message a second time if there is a chance it will succeed when
    retrtying.
    """
    upload_id = notification.metadata.upload_id
    if upload_id is None:
        # During the upload API migration, this probably means the upload was created with upload
        # API v1. We should simply ignore (and ack) the message in that case, since it doesn't.
        # need finalization.
        logger.info("could not determine upload id for key %s", notification.key)
        return
    try:
        upload = Upload.objects.get(id=upload_id)
    except Upload.DoesNotExist:
        # The object has an upload_id metadata field, but the upload does not exist. This should
        # not be possible.
        logger.error(
            "could not find upload with id %s for key %s", upload_id, notification.key
        )
        # Return without an exception so the message gets acked; reprocessing it won't help.
        return

    logger.info("processing upload id %s, key %s", upload_id, notification.key)
    metadata = notification.metadata
    sym_data = {}
    if is_sym_file(notification.key) and metadata.download_url:
        try:
            prefix = download_sym_file_prefix(metadata.download_url)
            sym_data = extract_sym_header_data(iter(prefix.splitlines()))
        except (UnicodeDecodeError, zlib.error, SymParseError):
            logger.exception("error while parsing .sym file: %s")

    # Use a database transaction to ensure idempotency.
    with transaction.atomic():
        # Atomically create the database entry for the file upload. This only creates a new row if
        # there isn't an entry for the same upload id and key yet. This translates into a `SELECT`
        # followed by an `INSERT`. If the `INSERT` fails due to the uniqueness constraint on
        # (`upload_id`, `key`), a matching row must have been created concurrently, and Django
        # will rerun the `SELECT` to query it.
        _, created = FileUpload.objects.get_or_create(
            upload=upload,
            key=notification.key,
            defaults=dict(
                # Since the upload is happening on the client side now, recording two timestamps
                # here no longer makes sense, and we should remove one of them once we
                # decommission version 1 of the upload API.
                created_at=notification.event_time,
                completed_at=notification.event_time,
                bucket_name=upload.bucket_name,
                update=notification.event_type == "finalize_update",
                compressed=should_compressed_key(notification.key),
                size=metadata.content_length,
                debug_filename=sym_data.get("debug_filename"),
                debug_id=sym_data.get("debug_id"),
                code_file=sym_data.get("code_file"),
                code_id=sym_data.get("code_id"),
                generator=sym_data.get("generator"),
            ),
        )
        if created:
            # We need to update the outstanding file upload counter _atomically_. This means
            # a) the decrement operation needs to be performed by the database itself to avoid
            #    data races and
            # b) we can only decrement the counter if it's still greater than zero.
            # The second part should always hold. We only hand out the number of upload session
            # URLs stored in `outstanding_file_uplads`, and each of these URLs can be used to
            # finalize and upload at most once. We could reach more than one noitification for
            # a finalized upload, but we can reach this branch of the `if` above only once for
            # each finalized upload.
            # If `outstanding_file_uploads` reaches zero, we mark the upload as completed by
            # setting `completed_at` to the time the last upload completed. This is handled on the
            # database side so we only need a single UPDATE. The condition sees the old value of
            # `outstanding_file_uploads`, so we check whether it's 1 rather than 0.
            # The resulting SQL for this `update()` call is roughly this:
            #
            #     UPDATE upload_upload
            #     SET
            #         outstanding_file_uploads = outstanding_file_uploads - 1,
            #         completed_at = CASE
            #             WHEN outstanding_file_uploads = 1 THEN %(event_time)s
            #             ELSE completed_at
            #         END
            #     WHERE id = %(upload_id)s
            #       AND outstanding_file_uploads > 0;
            updated = Upload.objects.filter(
                pk=upload_id, outstanding_file_uploads__gt=0
            ).update(
                outstanding_file_uploads=F("outstanding_file_uploads") - 1,
                completed_at=Case(
                    When(
                        outstanding_file_uploads=1,
                        then=notification.event_time,
                    ),
                    default=F("completed_at"),
                ),
            )
            if not updated:
                # This should not be possible. If it happens anyway, we should still create the
                # FileUpload and ack the message.
                logger.error(
                    "outstanding file upload count already 0 for upload id %s, key %s",
                    upload_id,
                    notification.key,
                )
            logger.info(
                "processing of upload id %s, key %s complete",
                upload_id,
                notification.key,
            )
        else:
            # This is possible because pub/sub messages can be delivered multiple times.
            logger.info(
                "database entry for upload id %s, key %s already exists",
                upload_id,
                notification.key,
            )


class ThreadLocalSession(threading.local):
    session: requests.Session

    def get(self) -> requests.Session:
        try:
            return self.session
        except AttributeError:
            self.session = session_with_retries()
            return self.session


# We want to use `requests.Session` objects to benefit from connection pooling, but they are not
# thread-safe, so we need to create one per thread.
SESSION = ThreadLocalSession()


def download_sym_file_prefix(url: str, gzipped_bytes: int = 2048) -> str:
    """Download a prefix of the .sym file at the given URL.

    We only need the first few INFO lines to extract information from them. These lines will
    typlically fit in about a hundred bytes. We will download the first few kilobytes of
    compressed data and decompress it, which ought to enough in all cases.
    """
    headers = {
        "Range": f"bytes=0-{gzipped_bytes - 1}",
        "Accept-Encoding": "gzip",
    }
    session = SESSION.get()
    with session.get(url, headers=headers, stream=True) as response:
        response.raise_for_status()
        # Since we only download a prefix of the file, it won't include the gxip trailer in most
        # cases. To prevent requests from erroring out because of that, we need to tell it not to
        # decode the stream, and we need to decompress it manually instead.
        response.raw.decode_content = False
        chunks = []
        remaining = gzipped_bytes
        while remaining:
            chunk = response.raw.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)

    decompressor = zlib.decompressobj(zlib.MAX_WBITS + 16)
    data = b"".join(decompressor.decompress(chunk) for chunk in chunks)
    # The data may end with incomplete Unicode bytes (though I'd hope it's generally ASCII), so we
    # need to decode the data with an incremental decoder.
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    return decoder.decode(data, final=False)
