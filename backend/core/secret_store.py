"""
backend/core/secret_store.py
Galaxy Vast AI -- Encrypted Secret Store (AES-256-GCM)
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)
MASTER_KEY_ENV = "MT5_MASTER_KEY"
_GCM_NONCE_LEN = 12


def _get_master_key() -> bytes:
    raw = os.getenv(MASTER_KEY_ENV, "")
    if not raw:
        logger.warning("%s not set -- using insecure default", MASTER_KEY_ENV)
        raw = "insecure-default-key-change-in-production"
    return hashlib.sha256(raw.encode()).digest()


try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    logger.warning("cryptography not installed -- SecretStore disabled")


class SecretStore:
    """AES-256-GCM secret store."""

    def __init__(self, master_key: Optional[bytes] = None) -> None:
        self._kek = master_key or _get_master_key()

    def encrypt(self, plaintext: str) -> str:
        if not _HAS_CRYPTO:
            raise RuntimeError("cryptography package is required")
        nonce = os.urandom(_GCM_NONCE_LEN)
        ct = AESGCM(self._kek).encrypt(nonce, plaintext.encode(), None)
        return base64.urlsafe_b64encode(nonce + ct).decode()

    def decrypt(self, token: str) -> str:
        if not _HAS_CRYPTO:
            raise RuntimeError("cryptography package is required")
        raw = base64.urlsafe_b64decode(token.encode())
        nonce = raw[:_GCM_NONCE_LEN]
        ct = raw[_GCM_NONCE_LEN:]
        return AESGCM(self._kek).decrypt(nonce, ct, None).decode()

    def rotate_key(self, new_master_key: bytes, encrypted_dek: str) -> str:
        """Re-encrypt a DEK under a new master key."""
        dek_plaintext = self.decrypt(encrypted_dek)
        return SecretStore(master_key=new_master_key).encrypt(dek_plaintext)


secret_store = SecretStore()
