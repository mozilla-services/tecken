#!/usr/bin/env bash

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -eo pipefail

# Set up pub/sub
pubsub-cli delete-topic "${PUBSUB_GCP_PROJECT}" "${PUBSUB_TOPIC_NAME}"
pubsub-cli create-topic "${PUBSUB_GCP_PROJECT}" "${PUBSUB_TOPIC_NAME}"
pubsub-cli create-subscription "${PUBSUB_GCP_PROJECT}" "${PUBSUB_TOPIC_NAME}" "${PUBSUB_SUBSCRIPTION_NAME}"

# Set up GCS
gcs-cli delete "${UPLOAD_GCS_BUCKET}"
gcs-cli create "${UPLOAD_GCS_BUCKET}"
gcs-cli notification "${UPLOAD_GCS_BUCKET}" "${PUBSUB_GCP_PROJECT}" "${PUBSUB_TOPIC_NAME}"

# Set up db
python bin/db.py drop || true
python bin/db.py create
python manage.py migrate --noinput
