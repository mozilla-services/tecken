# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
import logging
import os
from typing import Optional
from urllib.parse import quote

from requests import Session, Response
from requests.adapters import HTTPAdapter, Retry


LOGGER = logging.getLogger(__name__)


class AuthTokenMissing(Exception):
    pass


@dataclass
class Environment:
    """A target environment specification."""

    # The name of the environment
    name: str

    # The base URL of the Tecken instance to test.
    base_url: str

    # List of custom pytest marks to include
    include_marks: set[str]

    def env_var_name(self, try_storage: bool) -> str:
        env_var_name = self.name.upper() + "_AUTH_TOKEN"
        if try_storage:
            env_var_name += "_TRY"
        return env_var_name

    def auth_token(self, try_storage: bool) -> str:
        env_var_name = self.env_var_name(try_storage)
        try:
            return os.environ[env_var_name]
        except KeyError:
            kind = "try" if try_storage else "regular"
            raise AuthTokenMissing(
                f"environment variable {env_var_name} for {kind} uploads not set"
            ) from None


class TeckenRetry(Retry):
    """Retry class with customized backoff behavior and logging."""

    def get_backoff_time(self) -> float:
        # The standard Retry class uses a delay of 0 between the first and second attempt,
        # and exponential backoff after that.  We mostly need the retry behaviour for 429s,
        # so we should already wait after the first attempt, and we don't need exponential
        # backoff.
        if self.history and self.history[-1].status in self.status_forcelist:
            LOGGER.info("sleeping for 30 seconds...")
            return 30.0
        return 0.0

    def increment(self, *args, response=None, **kwargs) -> "TeckenRetry":
        if response and response.status >= 400:
            LOGGER.warning("response status code %s", response.status)
        return super().increment(*args, response=response, **kwargs)


class TeckenClient:
    def __init__(self, target_env: "Environment"):
        self.target_env = target_env
        self.base_url = target_env.base_url.removesuffix("/")
        self.session = Session()
        self.session.headers["User-Agent"] = "tecken-systemtests"
        retry = TeckenRetry(
            status=3, status_forcelist=[429, 502, 503, 504], allowed_methods=[]
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def auth_request(
        self,
        method: str,
        path: str,
        try_storage: bool = False,
        auth_token: Optional[str] = None,
        **kwargs,
    ) -> Response:
        if not auth_token:
            auth_token = self.target_env.auth_token(try_storage)
        headers = {"Auth-Token": auth_token}
        url = f"{self.base_url}{path}"
        return self.session.request(method, url, headers=headers, **kwargs)

    def download(
        self,
        sym_file_key: str,
        try_storage: bool = False,
        method: str = "GET",
        allow_redirects: bool = True,
    ) -> Response:
        url = f"{self.base_url}/{quote(sym_file_key)}"
        if try_storage:
            url += "?try"
        LOGGER.info("downloading %s", url)
        return self.session.request(method, url, allow_redirects=allow_redirects)

    def upload(self, file_name: os.PathLike, try_storage: bool = False) -> Response:
        LOGGER.info("uploading %s", file_name)
        with open(file_name, "rb") as f:
            files = {os.path.basename(file_name): f}
            return self.auth_request("POST", "/upload/", try_storage, files=files)

    def upload_by_download(self, url: str, try_storage: bool = False) -> Response:
        LOGGER.info("uploading by download from %s", url)
        return self.auth_request("POST", "/upload/", try_storage, data={"url": url})
