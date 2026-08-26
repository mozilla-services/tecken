# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from typing import cast
from unittest.mock import Mock

from google import pubsub_v1
from google.cloud.pubsub_v1.subscriber.message import Message
import pytest
from pytest_django.fixtures import SettingsWrapper

from tecken.base.symbolstorage import SymbolStorage
from tecken.ext.gcp import pubsub
from tecken.ext.gcp.storage import GCSStorage
from tecken.libstorage import Notification
from tecken.tests.utils import UPLOADS, Upload


class MessageWrapper:
    """Imitate a message created by streaming pub/sub subscriber.

    Messages passed to the callback by the streaming subscriber have ack() and nack() methods.
    There's no easy way of instantiating the internal type used for these messages, so we
    implement our own wrapper type.
    """

    def __init__(
        self,
        subscriber: pubsub_v1.SubscriberClient,
        subscription_path: str,
        received: pubsub_v1.ReceivedMessage,
    ):
        self.data = received.message.data
        self.attributes = received.message.attributes
        self._subscriber = subscriber
        self._subscription_path = subscription_path
        self._ack_id = received.ack_id
        self.acked = self.nacked = False

    def ack(self):
        self._subscriber.acknowledge(
            subscription=self._subscription_path, ack_ids=[self._ack_id]
        )
        self.acked = True

    def nack(self):
        # "Nacking" is performed by setting the ack deadline to zero.
        self._subscriber.modify_ack_deadline(
            subscription=self._subscription_path,
            ack_ids=[self._ack_id],
            ack_deadline_seconds=0,
        )
        self.nacked = True


def pull_and_process(
    settings: SettingsWrapper,
    gcs_pubsub_subscription: str,
    expect_call: bool = True,
    process_error: Exception | None = None,
) -> tuple[MessageWrapper, Notification | None]:
    with pubsub_v1.SubscriberClient() as subscriber:
        subscription_path = subscriber.subscription_path(
            settings.PUBSUB_GCP_PROJECT, gcs_pubsub_subscription
        )
        (received,) = subscriber.pull(
            subscription=subscription_path, max_messages=2
        ).received_messages
        process_mock = Mock(side_effect=process_error)
        message = MessageWrapper(subscriber, subscription_path, received)
        pubsub._subscription_callback(process_mock, cast(Message, message))
        if expect_call:
            process_mock.assert_called_once()
            return message, process_mock.call_args.args[0]
        else:
            process_mock.assert_not_called()
            return message, None


@pytest.mark.parametrize(("key", "upload"), UPLOADS.items())
def test_callback(
    settings: SettingsWrapper,
    symbol_storage: SymbolStorage,
    gcs_pubsub_subscription: str,
    key: str,
    upload: Upload,
):
    upload.upload(symbol_storage)
    message, notification = pull_and_process(settings, gcs_pubsub_subscription)

    assert message.acked
    assert not message.nacked
    assert notification.event_type == "finalize_new"
    assert notification.key == key
    metadata = notification.metadata
    assert metadata.content_length == len(upload.body)
    if upload.metadata.content_type is None:
        assert metadata.content_type == "application/octet-stream"
    else:
        assert metadata.content_type == upload.metadata.content_type
    assert metadata.content_encoding == upload.metadata.content_encoding
    assert metadata.original_content_length == len(upload.original_body)
    assert metadata.original_md5_sum == upload.md5_sum()
    assert metadata.download_url is not None and "generation=" in metadata.download_url
    assert metadata.upload_id is None

    # Upload the file again to verify that updates are detected correctly.
    upload.upload(symbol_storage)
    message, notification = pull_and_process(settings, gcs_pubsub_subscription)

    assert notification.event_type == "finalize_update"


def test_callback_backend_error(
    settings: SettingsWrapper,
    symbol_storage: SymbolStorage,
    gcs_pubsub_subscription: str,
    monkeypatch: pytest.MonkeyPatch,
):
    UPLOADS["ShowSSEConfig.exe/6A4B9A365000/ShowSSEConfig.sym"].upload(symbol_storage)

    def raise_backend_error(self: GCSStorage):
        raise RuntimeError("backend error")

    monkeypatch.setattr(GCSStorage, "_get_client", raise_backend_error)
    message, _ = pull_and_process(settings, gcs_pubsub_subscription, expect_call=False)

    assert not message.acked
    assert message.nacked


def test_callback_processing_error(
    settings: SettingsWrapper,
    symbol_storage: SymbolStorage,
    gcs_pubsub_subscription: str,
):
    UPLOADS["ShowSSEConfig.exe/6A4B9A365000/ShowSSEConfig.sym"].upload(symbol_storage)
    message, notification = pull_and_process(
        settings,
        gcs_pubsub_subscription,
        process_error=RuntimeError("processing error"),
    )

    assert notification is not None
    assert not message.acked
    assert message.nacked
