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
# There's an incompatibility between recent versions of the GCS Python client library and the
# gcs-emulator. The GCS client library renders topic paths in the format
#
#     //pubsub.googleapis.com/projects/{project}/topics/{topic-name}
#
# while the GCS emulator expects the format
#
#     projects/{project}/topics/{topic-name}
#
# The GCS client library is apparently using the newer format, and it's not supported by the GCS
# emulator yet. I filed a PR [1] to fix this in the emulator. In the meantime, we need to continue
# using the manual curl invocation I used for testing.
#
# [1]: https://github.com/fsouza/fake-gcs-server/pull/2318
#
# Once this is fixed in the emulator, we can switch to this command:
#
# gcs-cli notification "${UPLOAD_GCS_BUCKET}" "${PUBSUB_GCP_PROJECT}" "${PUBSUB_TOPIC_NAME}"
IFS= read -r -d '' notification_config <<EOF || true
{
    "topic": "projects/${PUBSUB_GCP_PROJECT}/topics/${PUBSUB_TOPIC_NAME}",
    "event_types": ["OBJECT_FINALIZE"],
    "payload_format": "JSON_API_V1"
}
EOF
curl --fail-with-body --silent --show-error -X POST \
    -H 'Content-Type: application/json' --data "${notification_config}" \
    "${STORAGE_EMULATOR_HOST}/storage/v1/b/${UPLOAD_GCS_BUCKET}/notificationConfigs"

# Set up db
python bin/db.py drop || true
python bin/db.py create
python manage.py migrate --noinput
