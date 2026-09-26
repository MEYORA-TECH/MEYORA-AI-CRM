"""Encryption for secrets at rest (OAuth refresh tokens). AES-256-GCM with a random nonce."""

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
VERSION = b"v1"


@lru_cache
def _key() -> bytes:
    s = get_settings()
    if s.encryption_key and s.encryption_key.get_secret_value().strip():
        key = base64.b64decode(s.encryption_key.get_secret_value())
        if len(key) != 32:
            raise RuntimeError("ENCRYPTION_KEY must be 32 bytes, base64-encoded")
        return key
    if s.is_production:
        raise RuntimeError("ENCRYPTION_KEY is required in production")
    # Development only: derive a stable key so local setups work without extra config.
    log.warning("encryption_key_derived_from_jwt_secret")
    return hashlib.sha256(b"meyora-dev-encryption:" + s.jwt_secret.get_secret_value().encode()).digest()


def encrypt(plaintext: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_key()).encrypt(nonce, plaintext.encode(), VERSION)
    return (VERSION + b":" + base64.urlsafe_b64encode(nonce + sealed)).decode()


def decrypt(token: str) -> str:
    version, _, body = token.encode().partition(b":")
    if version != VERSION:
        raise ValueError("unknown ciphertext version")
    raw = base64.urlsafe_b64decode(body)
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], VERSION).decode()
