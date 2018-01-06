# -*- coding: utf-8 -*-
"""
Logging.
"""

import logging
import sys


# path to the log file
LOGFILE = None


def log_init(logfile: str):
    """Initializes logging."""
    if not logfile:
        return

    try:
        logging.basicConfig(filename=logfile, level=logging.DEBUG)
        global LOGFILE
        LOGFILE = logfile
    except EnvironmentError as emsg:
        print(str(emsg), file=sys.stderr)


def logit(message: str, level='info'):
    """Logs message."""
    if not LOGFILE:
        return

    method = getattr(logging, level.lower())

    try:
        for each_line in message.splitlines():
            method(each_line)
    except EnvironmentError as emsg:
        print(str(emsg), file=sys.stderr)
