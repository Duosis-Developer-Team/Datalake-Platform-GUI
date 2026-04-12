"""Fernet decrypt compatible with Datalake-Platform-GUI src/auth/crypto.py."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app import config


def _fernet() -> Fernet:
    raw = (config.FERNET_KEY or config.SECRET_KEY or "insecure-dev").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def fernet_decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
