# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

"""
Utilities for logging configuration and usage.
"""

import logging
import logging.config
import socket


_IS_LOGGING_SETUP = False


def setup_logging(app_config, processname):
    """Initialize Python logging configuration."""
    global _IS_LOGGING_SETUP
    if _IS_LOGGING_SETUP:
        # NOTE(willkg): This makes it so that logging is only set up once per process.
        return

    host_id = app_config("host_id") or socket.gethostname()

    class AddHostID(logging.Filter):
        def filter(self, record):
            record.host_id = host_id
            return True

    class AddProcessName(logging.Filter):
        def filter(self, record):
            record.processname = processname
            return True

    dc = {
        "version": 1,
        "disable_existing_loggers": True,
        "filters": {
            "add_hostid": {"()": AddHostID},
            "add_processname": {"()": AddProcessName},
        },
        "formatters": {
            "app": {
                "format": "%(asctime)s %(levelname)s - %(processname)s - %(name)s - %(message)s"
            },
            "mozlog": {
                "()": "dockerflow.logging.JsonLogFormatter",
                "logger_name": "eliot",
            },
        },
        "handlers": {
            "console": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "app",
                "filters": ["add_hostid", "add_processname"],
            },
            "mozlog": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "mozlog",
                "filters": ["add_hostid", "add_processname"],
            },
        },
        "loggers": {
            "eliot": {
                "level": app_config("logging_level"),
            }
        },
        "root": {"handlers": ["mozlog"], "level": "WARNING"},
    }

    if app_config("local_dev_env"):
        # In a local development environment, we log to the console in a human-readable
        # fashion and add a markus logger
        dc["loggers"]["markus"] = {"level": "INFO"}
        dc["root"]["handlers"] = ["console"]

    logging.config.dictConfig(dc)
    _IS_LOGGING_SETUP = True


def log_config(logger, component):
    """Log configuration for a given component."""
    for ns, key, val, opt in component.get_runtime_config():
        if ns:
            namespaced_key = "%s_%s" % ("_".join(ns), key)
        else:
            namespaced_key = key

        namespaced_key = namespaced_key.upper()

        if "secret" in opt.key.lower() and val:
            msg = "%s=*****" % namespaced_key
        else:
            msg = "%s=%s" % (namespaced_key, val)
        logger.info(msg)
