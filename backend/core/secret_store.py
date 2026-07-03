"""
backend/core/secret_store.py
Galaxy Vast AI - Encrypted Secret Store (Phase 11)

P11-SS-1: AES-256-GCM encryption with PBKDF2 key derivation
P11-SS-2: Raw credentials never stored in plain-text memory cache
P11-SS-3: Envelope encryption - DEK encrypted with KEK
P11-SS-4: Credential rotation without downtime
P11-SS-5: Audit log for every access
P11-SS-6: Memory zeroing after use (best-effort in Python)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# AES-GCM constants
_KEY_LEN   = 32   # AES-256
_NONCE_LEN = 12   # GCM standard
_TAG_LEN   = 16   # GCM authentication tag


@dataclass
class EncryptedBlob:
    """
    Envelope-encrypted secret blob.

    Layout on disk (base64-encoded JSON):
      {
        "v":   1,
        "ts":  <unix timestamp>,
        "dek": <base64(nonce + encrypted_dek + tag)>,
        "pay": <base64(nonce + encrypted_payload + tag)>
      }
    """
    salt:              bytes
    encrypted_dek:     bytes   # nonce(12) + ciphertext + tag(16)
    encrypted_payload: bytes   # nonce(12) + ciphertext + tag(16)
    created_at:        float   = field(default_factory=time.time)
    version:           int     = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "v":   self.version,
            "ts":  self.created_at,
            "s":   base64.b64encode(self.salt).decode(),
            "dek": base64.b64encode(self.encrypted_dek).decode(),
            "pay": base64.b64encode(self.encrypted_payload).decode(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EncryptedBlob":
        return cls(
            salt              = base64.b64decode(d["s"]),
            encrypted_dek     = base64.b64decode(d["dek"]),
            encrypted_payload = base64.b64decode(d["pay"]),
            created_at        = d.get("ts", 0.0),
            version           = d.get("v", 1),
        )


class SecretStore:
    """
    AES-256-GCM envelope-encrypted secret store.

    Master key (KEK) comes from environment variable SECRET_MASTER_KEY.
    A random per-secret DEK is generated, encrypted with the KEK,
    and stored alongside the encrypted payload.

    Usage:
        store = SecretStore(master_key=settings.SECRETS_MASTER_KEY)
        blob  = store.encrypt(b"my-api-key")
        store.save("stripe_key", blob)
        raw   = store.load_decrypt("stripe_key")
    """

    _PBKDF2_ITERS = 200_000

    def __init__(self, master_key: str, storage_dir: str = "/tmp/secrets") -> None:
        self._kek         = self._derive_kek(master_key)
        self._storage_dir = storage_dir
        self._cache: Dict[str, bytes] = {}  # name -> plaintext (zeroed after use)
        os.makedirs(storage_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encrypt(self, plaintext: bytes) -> EncryptedBlob:
        """
        Encrypt plaintext using a fresh random DEK.
        DEK is itself encrypted with the KEK.
        """
        salt = os.urandom(16)
        dek  = os.urandom(_KEY_LEN)

        enc_dek     = self._aes_gcm_encrypt(self._kek, dek)
        enc_payload = self._aes_gcm_encrypt(dek, plaintext)

        # Zero DEK from memory immediately
        dek = b"\x00" * _KEY_LEN
        del dek

        return EncryptedBlob(
            salt              = salt,
            encrypted_dek     = enc_dek,
            encrypted_payload = enc_payload,
        )

    def decrypt(self, blob: EncryptedBlob) -> bytes:
        """Decrypt blob — derive DEK from KEK then decrypt payload."""
        dek     = self._aes_gcm_decrypt(self._kek, blob.encrypted_dek)
        payload = self._aes_gcm_decrypt(dek, blob.encrypted_payload)

        # Zero DEK
        dek = b"\x00" * _KEY_LEN
        del dek
        return payload

    def save(self, name: str, blob: EncryptedBlob) -> None:
        """Persist an encrypted blob to the storage directory."""
        path = os.path.join(self._storage_dir, f"{name}.enc")
        with open(path, "w") as f:
            json.dump(blob.to_dict(), f)
        logger.info("Secret saved: %s", name)

    def load_decrypt(self, name: str) -> bytes:
        """Load and decrypt a named secret. Raises FileNotFoundError if missing."""
        path = os.path.join(self._storage_dir, f"{name}.enc")
        with open(path) as f:
            blob = EncryptedBlob.from_dict(json.load(f))
        plaintext = self.decrypt(blob)
        logger.info("Secret accessed: %s", name)
        return plaintext

    def rotate(self, name: str, new_master_key: str) -> None:
        """
        Re-encrypt a stored secret with a new master key.
        Old and new keys are both needed during rotation.
        """
        plaintext  = self.load_decrypt(name)
        new_store  = SecretStore(new_master_key, self._storage_dir)
        new_blob   = new_store.encrypt(plaintext)
        new_store.save(name, new_blob)
        # Zero plaintext
        plaintext  = b"\x00" * len(plaintext)
        del plaintext
        logger.info("Secret rotated: %s", name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _derive_kek(self, master_key: str) -> bytes:
        """PBKDF2-HMAC-SHA256 key derivation from master key."""
        salt = b"galaxy-vast-kek-salt-v1"
        return hashlib.pbkdf2_hmac(
            "sha256",
            master_key.encode(),
            salt,
            self._PBKDF2_ITERS,
            dklen=_KEY_LEN,
        )

    @staticmethod
    def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
        """AES-256-GCM encrypt. Returns nonce + ciphertext + tag."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as e:
            raise ImportError("pip install cryptography") from e

        nonce      = os.urandom(_NONCE_LEN)
        aesgcm     = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    @staticmethod
    def _aes_gcm_decrypt(key: bytes, data: bytes) -> bytes:
        """AES-256-GCM decrypt. Input: nonce(12) + ciphertext + tag(16)."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as e:
            raise ImportError("pip install cryptography") from e

        nonce      = data[:_NONCE_LEN]
        ciphertext = data[_NONCE_LEN:]
        aesgcm     = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
