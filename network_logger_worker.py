# -*- coding: utf-8 -*-
"""
Worker process for the QGIS Network Logger plugin.

The worker runs in a plain Python environment (no QGIS dependencies) and
streams JSON payloads from stdin into a rotating log file.
"""

from logging.handlers import RotatingFileHandler
import logging
import json
import sys


def _configure_logger(file_path):
    """
    Create a logger QgisNetworkLoggerWorker where files are 1MB max with 3 backup files.
    """
    handler = RotatingFileHandler(
        file_path, maxBytes=1 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s \t %(message)s", "%Y-%m-%d %H:%M:%S"))

    worker_logger = logging.getLogger("QgisNetworkLoggerWorker")
    worker_logger.setLevel(logging.INFO)
    worker_logger.handlers = []
    worker_logger.addHandler(handler)
    return worker_logger


def run_worker(file_path):
    """
    Call the function to create the logger and then loop over stdin.
    If read a __STOP__ brake the for loop and the process will close.
    Otherwise it load the json msg and write down the content to the log file.
    """
    logger = _configure_logger(file_path)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line == "__STOP__":
            break
        try:
            payload = json.loads(line)
            logger.info(
                "\t".join(
                    [
                        payload.get("event", ""),
                        str(payload.get("request_id", "")),
                        payload.get("operation", ""),
                        payload.get("url", ""),
                        str(payload.get("status", "")),
                        payload.get("details", ""),
                        payload.get("headers", ""),
                    ]
                )
            )
        except Exception:
            continue


def _usage_and_exit():
    """
    Helper to tell the user how to run the logger if wrong number of argument are provided.
    """
    msg = "Usage: python network_logger_worker.py <log-file-path>"
    print(msg, file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        _usage_and_exit()
    run_worker(sys.argv[1])
