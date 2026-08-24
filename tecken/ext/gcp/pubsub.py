# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from collections.abc import Callable
import datetime
import json
import logging
from threading import Event

from google.cloud import pubsub_v1

from tecken.base.symbolstorage import symbol_storage
from tecken.ext.gcp.storage import GCSStorage
from tecken.ext.gcp.utils import build_object_metadata
from tecken.libstorage import Notification, NotificationQueue

logger = logging.getLogger("tecken")


class GoogleNotificationQueue(NotificationQueue):
    """An implementation of the NotificationQueue interface for Google Cloud Pub/Sub."""

    def __init__(self, project_id: str, subscription_name: str):
        self.project_id = project_id
        self.subscription_name = subscription_name

    def subscribe(
        self,
        process: Callable[[Notification], None],
        stop_event: Event | None = None,
    ):
        """Subscribe to storage object notifications.

        This function calls the provided function for each received notification. If the callback
        finishes without error, the message is automatically acknowledged. If the callback throws
        an exception, the message is "nacked", resulting in its eventual redelivery (after the
        configured back-off time).

        :arg process: a function taking and processing a Notification instance.
        :arg stop_event: an optional event used to stop the subscription gracefully.
        """

        def callback(message):
            """Callback called for each pub/sub message.

            This function should only throw exceptions for temporary errors. An exception results
            in the message being nacked, so we will receive it again, and it's pointless to
            reprocess a message causing a permanent error, i.e. an error that will definitely
            occur again next time. (The pub/sub queue is configured with a maximum number of
            delivery attempts, so permament errors won't cause infinite loops, just unnecessary
            reprocessing.)
            """
            if message.attributes.get("eventType") != "OBJECT_FINALIZE":
                # The notifications should be configured to only send messages for events of this
                # type, but it doesn't hurt double checking.
                message.ack()
                return

            try:
                data = json.loads(message.data)
                if "overwroteGeneration" in message.attributes:
                    event_type = "finalize_update"
                else:
                    event_type = "finalize_new"
                event_time = datetime.datetime.fromisoformat(
                    message.attributes["eventTime"]
                )
                metadata = build_object_metadata(
                    size=int(data["size"]),
                    md5_hash=data["md5Hash"],
                    gcs_metadata=data.get("metadata") or {},
                )
                last_modified = data.get("customTime") or data.get("updated")
                if last_modified is not None:
                    metadata.last_modified = datetime.datetime.fromisoformat(
                        last_modified
                    )
                metadata.content_type = data.get("contentType")
                metadata.content_encoding = data.get("contentEncoding")
                key = message.attributes["objectId"]
                try_symbols = key.startswith("try/")
                key = key.removeprefix("try/").removeprefix("v1/")
                storage = symbol_storage()
                for backend in storage.get_download_backends(try_symbols):
                    if (
                        isinstance(backend, GCSStorage)
                        and backend.try_symbols == try_symbols
                        and backend.bucket == message.attributes["bucketId"]
                    ):
                        try:
                            base_url = backend.get_download_url(key)
                        except Exception:
                            # Exceptions during this call are potentially temporary, so we should
                            # nack the message and bail out.
                            logger.exception("exception while building download URL")
                            message.nack()
                            return
                        # We need to include the object's generation in the URL to avoid potential
                        # race conditions when the same file is uploaded multiple times in rapid
                        # succession.
                        generation = message.attributes["objectGeneration"]
                        metadata.download_url = f"{base_url}?generation={generation}"
                        # There can only be one matching backend, so let's break once we found it.
                        break
            except Exception:
                # The message somehow could not be parsed. It's body isn't valid JSON, it's missing
                # a required attribute or similar. It doesn't make sense to retry this message –
                # the parse error won't go away next time. So we simply ack the message and log the
                # exception.
                logger.exception("error extracting data from pub/sub message")
                message.ack()
                return
            notification = Notification(
                event_type=event_type,
                event_time=event_time,
                key=key,
                metadata=metadata,
            )
            try:
                process(notification)
            except Exception:
                message.nack()
            else:
                message.ack()

        with pubsub_v1.SubscriberClient() as subscriber:
            subscription_path = subscriber.subscription_path(
                self.project_id, self.subscription_name
            )
            future = subscriber.subscribe(subscription_path, callback=callback)
            try:
                if stop_event is None:
                    future.result()
                else:
                    while not stop_event.wait(0.1):
                        if future.done():
                            future.result()
                            return
            finally:
                future.cancel()
                future.result(timeout=10)
