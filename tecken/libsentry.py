# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import dataclasses
import importlib
import logging
from urllib.parse import urlparse, parse_qsl, urlencode
import sys
from typing import Any, Callable, Generator, Optional, Union

import markus
import sentry_sdk
from sentry_sdk.integrations.logging import ignore_logger


SENTRY_MODULE_NAME = __name__
metrics = markus.get_metrics(SENTRY_MODULE_NAME)
logger = logging.getLogger(SENTRY_MODULE_NAME)


MASK_TEXT: str = "[Scrubbed]"


ALL_COOKIE_KEYS: Any = object()
ALL_QUERY_STRING_KEYS: Any = object()


def get_sentry_base_url(sentry_dsn: str) -> str:
    """Given a sentry_dsn, returns the base url

    This is helpful for tests that need the url to the fakesentry api.

    :arg sentry_dsn: the sentry base url

    """
    if not sentry_dsn:
        raise Exception("sentry_dsn required")

    parsed_dsn = urlparse(sentry_dsn)
    netloc = parsed_dsn.netloc
    if "@" in netloc:
        netloc = netloc[netloc.find("@") + 1 :]

    return f"{parsed_dsn.scheme}://{netloc}/"


def scrub(value: str) -> str:
    """Scrub a value"""
    return MASK_TEXT


def build_scrub_cookies(params: list[str]) -> Callable:
    """Scrub specified keys in HTTP request cookies

    Sentry says the cookies can be:

    * an unparsed string
    * a dictionary
    * a list of tuples

    For the unparsed string, this parses it and figures things out.

    For dictionary and list of tuples, this returns the scrubbed forms of those.

    If the specified params is ALL_COOKIE_KEYS, then this will filter all cookie values.

    """

    def _scrub_cookies(value: Union[str, dict, list]) -> Union[str, dict, list]:
        to_scrub = params

        if not value:
            return value

        if isinstance(value, dict):
            if to_scrub is ALL_COOKIE_KEYS:
                value = {key: MASK_TEXT for key in value.keys()}
                return value

            for param in to_scrub:
                if param in value:
                    value[param] = MASK_TEXT
            return value

        if isinstance(value, list):
            if to_scrub is ALL_COOKIE_KEYS:
                value = [(pair[0], MASK_TEXT) for pair in value]
                return value

            for i, pair in enumerate(value):
                if pair[0] in to_scrub:
                    value[i] = (pair[0], MASK_TEXT)
            return value

        has_scrubbed_item = False
        scrubbed_pairs = []
        for cookie in value.split(";"):
            name, val = cookie.split("=", 1)
            name = name.strip()
            val = val.strip()

            if to_scrub is ALL_COOKIE_KEYS or name in to_scrub:
                if val:
                    val = MASK_TEXT
                    has_scrubbed_item = True
            scrubbed_pairs.append((name, val))

        if not has_scrubbed_item:
            return value

        return "; ".join(["=".join(pair) for pair in scrubbed_pairs])

    return _scrub_cookies


def build_scrub_query_string(params: list[str]) -> Callable:
    """Scrub specified keys in an HTTP request query_string

    Sentry says the query_string can be:

    * an unparsed string
    * a dictionary
    * a list of tuples

    For the unparsed string, this parses it and figures things out. If there's nothing
    that needs to be scrubbed, then it returns the original string. Otherwise it
    returns a query_string value with the items scrubbed, and reformed into a
    query_string. This sometimes means that other things in the string have changed and
    that may make debugging issues a little harder.

    For dictionary and list of tuples, this returns the scrubbed forms of those.

    If the params is ALL_QUERY_STRING_KEYS, then this will drop the query_string
    altogether.

    .. Note::

       The Sentry docs say that the query_string could be part of the url. This doesn't
       handle that situation.

    """

    def _scrub_query_string(value: Union[str, list, dict]) -> Union[str, list, dict]:
        to_scrub = params
        if not value:
            return value

        if isinstance(value, dict):
            if to_scrub is ALL_QUERY_STRING_KEYS:
                value = {key: MASK_TEXT for key in value.keys()}
                return value

            for param in to_scrub:
                if param in value:
                    value[param] = MASK_TEXT
            return value

        if isinstance(value, list):
            if to_scrub is ALL_QUERY_STRING_KEYS:
                value = [(pair[0], MASK_TEXT) for pair in value]
                return value

            for i, pair in enumerate(value):
                if pair[0] in to_scrub:
                    value[i] = (pair[0], MASK_TEXT)
            return value

        has_scrubbed_item = False
        scrubbed_pairs = []
        for name, val in parse_qsl(value, keep_blank_values=True):
            if to_scrub is ALL_QUERY_STRING_KEYS or name in to_scrub:
                if val:
                    val = MASK_TEXT
                    has_scrubbed_item = True
            scrubbed_pairs.append((name, val))

        if not has_scrubbed_item:
            return value

        return urlencode(scrubbed_pairs)

    return _scrub_query_string


@dataclasses.dataclass
class ScrubRule:
    """

    ``key_path`` is a Python dotted path of key names with ``[]`` to denote
    arrays to traverse pointing to a dict with values to scrub.

    ``keys`` is a list of keys to scrub values of

    ``scrub_function`` is a callable that takes a value and returns a scrubbed value.
    For example::

        def hide_letter_a(value):
            return "".join([letter if letter != "a" else "*" for letter in value])


    ScrubRule example::

        ScrubRule(
            key_path="request.data",
            keys=["csrfmiddlewaretoken"],
            scrub_function=scrub
        )

    """

    key_path: str
    keys: list[str]
    scrub_function: Union[str, Callable]

    def __post_init__(self):
        self._key_path_list = self.key_path.split(".")

        fn = self.scrub_function
        if not callable(fn):
            if fn in globals():
                # If it's global in this module, then pull that
                fn = globals()[fn]
            elif "." in fn:
                module_name, class_name = fn.rsplit(".", 1)
                module = importlib.import_module(module_name)
                fn = getattr(module, class_name)
        self._scrub = fn


SCRUB_RULES_DEFAULT: list[ScrubRule] = [
    # Hide stacktrace variables
    ScrubRule(
        key_path="exception.values.[].stacktrace.frames.[].vars",
        keys=["username", "password"],
        scrub_function=scrub,
    ),
]


def get_target_dicts(event: dict, key_path: list[str]) -> Generator[dict, None, None]:
    """Given a key_path, yields the target dicts.

    Keys should be dict keys. To traverse all the items in an array value, use ``[]``.

    With this event::

        {
            "request": { ... },
            "exception": {
                "stacktrace": {
                    "frames": [
                        {"name": "frame1", "vars": { ... }},
                        {"name": "frame2", "vars": { ... }},
                        {"name": "frame3", "vars": { ... }},
                        {"name": "frame4", "vars": { ... }},
                    ]
                }
            }
        }

    Example key_path values::

        ["request"]
        ["exception", "stacktrace", "frames", "[]", "vars"]

    """
    parent = event
    for i, part in enumerate(key_path):
        if part == "[]" and isinstance(parent, (tuple, list)):
            for item in parent:
                yield from get_target_dicts(item, key_path[i + 1 :])
            return

        elif part in parent:
            parent = parent[part]

    if isinstance(parent, dict):
        yield parent


class Scrubber:
    """Scrubber pipeline for Sentry events

    https://docs.sentry.io/platforms/python/configuration/filtering/

    """

    def __init__(self, scrub_rules: list[ScrubRule] = SCRUB_RULES_DEFAULT):
        """
        :arg scrub_keys: list of ScrubRule instances

        """
        self.scrub_rules = scrub_rules

    def __call__(self, event: dict, hint: Any) -> dict:
        """Implements before_send function interface and scrubs Sentry event

        This tries really hard to be very defensive such that even if there are bugs in
        the scrubs, it still emits something to Sentry.

        It will log errors, so we should look for those log statements. They'll all have
        "LIBSENTRYERROR" in the message making them easy to find regardless of the
        logger name.

        Further, they emit two incr metrics:

        * scrub_fun_error
        * get_target_dicts_error

        Put those in a dashboard with alerts so you know when to look in the logs.

        """

        for rule in self.scrub_rules:
            try:
                for parent in get_target_dicts(event, rule._key_path_list):
                    if not parent:
                        continue

                    for key in rule.keys:
                        if key not in parent:
                            continue

                        val = parent[key]

                        try:
                            filtered_val = rule._scrub(val)
                        except Exception:
                            logger.exception(f"LIBSENTRYERROR: Error in {rule._scrub}")
                            metrics.incr("scrub_fun_error")
                            filtered_val = "ERROR WHEN SCRUBBING"

                        parent[key] = filtered_val
            except Exception:
                logger.exception("LIBSENTRYERROR: Error in get_target_dicts")
                metrics.incr("get_target_dicts_error")

        return event


def set_up_sentry(
    release: str,
    host_id: str,
    sentry_dsn: str,
    integrations: list[Any] = None,
    before_send: Callable = None,
    **kwargs,
):
    """Set up Sentry

    By default, this will set up default integrations
    (https://docs.sentry.io/platforms/python/configuration/integrations/default-integrations/),
    but not the auto-enabling ones.

    :arg release: the release name to tag events with
    :arg host_id: some str representing the host this service is running on
    :arg sentry_dsn: the Sentry DSN
    :arg integrations: list of sentry integrations to set up;
    :arg before_send: set this to a callable to handle the Sentry before_send hook

        For scrubbing, do something like this::

            scrubber = Scrubbing(scrub_keys=SCRUB_RULES_DEFAULT + my_scrub_rules)

        and then pass that as the ``before_send`` value.

    :arg kwargs: any additional arguments to pass to sentry_sdk.init()

    """
    if not sentry_dsn:
        return

    sentry_sdk.init(
        dsn=sentry_dsn,
        release=release,
        send_default_pii=False,
        server_name=host_id,
        # This prevents Sentry from trying to enable all the auto-enabling
        # integrations. We only want the ones we explicitly set up. This
        # provents sentry from loading the Falcon integration (which fails) in a Django
        # context.
        auto_enabling_integrations=False,
        integrations=integrations or [],
        before_send=before_send or None,
        **kwargs,
    )

    # Ignore logging from this module
    ignore_logger(SENTRY_MODULE_NAME)


def is_enabled() -> bool:
    """Return True if sentry was initialized with a DSN"""
    return (
        sentry_sdk.Hub.current.client
        and sentry_sdk.Hub.current.client.options["dsn"] is not None
    )


def get_hub() -> sentry_sdk.Hub:
    """Get the initialized Sentry hub.

    With a previous SDK (raven), this was called get_client, and initialized
    the it with a DSN. With the current SDK, this returns the Hub, and is
    mostly used to give tests something to test against.

    """
    return sentry_sdk.Hub.current


def capture_error(
    use_logger: Optional[logging.Logger] = None,
    exc_info: Optional[Any] = None,
    extra: dict[str, Any] = None,
):
    """Capture an error to send to Sentry

    If Sentry is configured, this will send it using capture_exception().

    If Sentry is not enabled, this will log it to the logger.

    :arg use_logger: the logger to use; defaults to the logger for this module
    :arg exc_info: the exception information as a tuple like from ``sys.exc_info``
    :arg extra: dict holding additional information to add to the scope before
        capturing this exception

    """
    use_logger = use_logger or logger

    exc_info = exc_info or sys.exc_info()

    if is_enabled():
        extra = extra or {}

        try:
            # Get the configured Sentry hub
            hub = get_hub()

            with sentry_sdk.push_scope() as scope:
                for key, value in extra.items():
                    scope.set_extra(key, value)

                # Send the exception.
                identifier = hub.capture_exception(error=exc_info)
                use_logger.info("Error captured in Sentry! Reference: %s" % identifier)

                # At this point, if everything is good, the exceptions were
                # successfully sent to sentry and we can return.
                return
        except Exception:
            # Log the exception from trying to send the error to Sentry.
            use_logger.error("Unable to report error with Sentry", exc_info=True)

    # Sentry isn't configured or it's busted, so log the error we got that we
    # wanted to capture.
    use_logger.warning("Sentry has not been configured and an exception happened")
    use_logger.error("Exception occurred", exc_info=exc_info)
