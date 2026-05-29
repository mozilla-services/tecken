# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from google.cloud import iam_credentials


class ClientOTelConfigProvider:
    """Provider for the OTel config returned by the /upload/auth_info/ endpoint."""

    def __init__(
        self,
        service_account: str,
        gcp_project: str,
        gcp_region: str,
        log_level: str,
        iam_client=None,
    ):
        self.service_account = service_account
        self.gcp_project = gcp_project
        self.gcp_region = gcp_region
        self.log_level = log_level
        self.iam_client = iam_client or iam_credentials.IAMCredentialsClient()

    def get(self, user_id: int) -> dict:
        """Return the OTel config.

        Each call to this function generates a new access token for the OTel service
        account that's valid for one hour.
        """
        access_token = self.iam_client.generate_access_token(
            name=self.service_account,
            scope=["https://www.googleapis.com/auth/cloud-platform"],
        ).access_token

        # The consumer of this configuration, the upload-symbols client, assumes the
        # OTLP collector is using the http/protobuf OTLP protocol, but it doesn't make
        # any other assumptions about the collector.
        return {
            "endpoint": "https://telemetry.googleapis.com/",
            "headers": {"Authorization": f"Bearer {access_token}"},
            "resource_attributes": {
                "gcp.project_id": self.gcp_project,
                "location": self.gcp_region,
                "user.id": user_id,
            },
            "log_level": self.log_level,
        }


CONFIG: ClientOTelConfigProvider | None = None


def init(service_account: str, gcp_project: str, gcp_region: str, log_level: str):
    """Initialize the global OTel config provider."""
    global CONFIG
    CONFIG = ClientOTelConfigProvider(
        service_account, gcp_project, gcp_region, log_level
    )
