"""Logging helper.

Provides a single ``setup_logger`` factory that returns a configured logger
writing to stdout with a consistent format. Guards against attaching duplicate
handlers when called repeatedly for the same logger name.
"""

import logging
import sys

_LOG_FORMAT = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"


def setup_logger(name):
    """Return a logger that streams to stdout.

    Calling this multiple times with the same ``name`` will not stack handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Guard against duplicate handlers on repeated calls.
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)

    # Avoid double emission through the root logger.
    logger.propagate = False
    return logger
