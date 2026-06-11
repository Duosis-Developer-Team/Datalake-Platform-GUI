"""Logging configuration for chatbot-api.

Logs are metadata-only by policy (see audit_service): request_id, user id, tool
names, latency, status. Raw prompts / secrets are never logged by default.
"""

from __future__ import annotations

import logging
import os
import sys

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers under uvicorn reload / repeated imports.
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
