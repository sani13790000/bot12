"""
backend/core/field_encryption.py
Galaxy Vast AI — Database Field-Level Encryption (Phase 11)

P11-FE-1: AES-256-GCM encryption برای فیلدهای حساس DB
P11-FE-2: License keys، MT5 passwords، API tokens رمزنگاری شوند
P11-FE-3: Format: "enc:v1:<base64(nonce+ct+tag)>" — قابل تشخیص
P11-FE-4: Transparent encrypt/decrypt در Pydantic validators
P11-FE-5: Key rotation — decrypt با old key، encrypt با new key
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
from typing import Optional

_PREFIX = "enc:v1:"
_NONCE = 12
_TAG = 16
_KEY_LEN = 32


class FieldEncryption:
    """
    Transparent field-level encryption for database storage.

    Usage:
        fe = FieldEncryption.from_env()
        stored = fe.encrypt("my-secret")    # "enc:v1:BASE64..."
        plain  = fe.decrypt(stored)          # "my-secret"
        plain2 = fe.decrypt("already-plain") # passthrough
    """

    def __init__(self, key: bytes) -> None:
        if len(key) != _KEY_LEN:
            raise ValueError(f"FieldEncryption key must be {_KEY_LEN} bytes, got {len(key)}")
        self._key = key

    @classmethod
    def from_env(cls, env_var: str = "FIELD_ENCRYPTION_KEY") -> "FieldEncryption":
        """P11-FE-1: Load key from environment (64 hex chars = 32 bytes)."""
        hex_key = os.environ.get(env_var, "")
        if not hex_key:
            jwt = os.environ.get("JWT_SECRET_KEY", "dev-insecure")
            key = hashlib.sha256(jwt.encode()).digest()
            import logging

            logging.getLogger(__name__).warning(
                "P11-FE-WARN: FIELD_ENCRYPTION_KEY not set — using derived dev key. "
                "Set FIELD_ENCRYPTION_KEY in production!"
            )
            return cls(key)
        try:
            key = bytes.fromhex(hex_key)
        except ValueError:
            raise ValueError("FIELD_ENCRYPTION_KEY must be valid hex")
        return cls(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext → 'enc:v1:BASE64...' format."""
        if not plaintext:
            return plaintext
        if plaintext.startswith(_PREFIX):
            return plaintext  # already encrypted
        raw = self._raw_encrypt(plaintext.encode())
        return _PREFIX + base64.b64encode(raw).decode()

    def decrypt(self, value: str) -> str:
        """Decrypt 'enc:v1:...' → plaintext. Passthrough for unencrypted values."""
        if not value or not value.startswith(_PREFIX):
            return value  # passthrough
        raw = base64.b64decode(value[len(_PREFIX) :])
        return self._raw_decrypt(raw).decode()

    def is_encrypted(self, value: str) -> bool:
        """Return True if value is an encrypted field."""
        return isinstance(value, str) and value.startswith(_PREFIX)

    def rotate(self, encrypted_value: str, new_key: bytes) -> str:
        """P11-FE-5: Decrypt with current key, re-encrypt with new key."""
        plain = self.decrypt(encrypted_value)
        new_fe = FieldEncryption(new_key)
        return new_fe.encrypt(plain)

    # ── Internal crypto ──────────────────────────────────────────────────────

    def _raw_encrypt(self, plaintext: bytes) -> bytes:
        """AES-256-GCM or fallback HMAC-SIV encrypt. Returns nonce+ct+tag."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = secrets.token_bytes(_NONCE)
            ct_tag = AESGCM(self._key).encrypt(nonce, plaintext, None)
            return nonce + ct_tag
        except ImportError:
            pass
        # Fallback: HMAC-based stream cipher
        nonce = secrets.token_bytes(_NONCE)
        ks = self._keystream(nonce, len(plaintext))
        ct = bytes(p ^ k for p, k in zip(plaintext, ks))
        tag = hmac.new(self._key, nonce + ct, hashlib.sha256).digest()[:_TAG]
        return nonce + ct + tag

    def _raw_decrypt(self, data: bytes) -> bytes:
        """Decrypt and verify. Raises ValueError on tamper."""
        if len(data) < _NONCE + _TAG:
            raise ValueError("Encrypted field too short")
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce, ct_tag = data[:_NONCE], data[_NONCE:]
            try:
                return AESGCM(self._key).decrypt(nonce, ct_tag, None)
            except Exception:
                raise ValueError("Field decryption failed — data tampered or wrong key")
        except ImportError:
            pass
        nonce = data[:_NONCE]
        ct = data[_NONCE:-_TAG]
        tag = data[-_TAG:]
        mac = hmac.new(self._key, nonce + ct, hashlib.sha256).digest()[:_TAG]
        if not hmac.compare_digest(mac, tag):
            raise ValueError("Field decryption failed — data tampered or wrong key")
        ks = self._keystream(nonce, len(ct))
        return bytes(c ^ k for c, k in zip(ct, ks))

    def _keystream(self, nonce: bytes, length: int) -> bytes:
        out, ctr = b"", 0
        while len(out) < length:
            out += hmac.new(self._key, nonce + struct.pack(">Q", ctr), hashlib.sha256).digest()
            ctr += 1
        return out[:length]


# ── Global instance (lazy) ────────────────────────────────────────────────────
_fe: Optional[FieldEncryption] = None


def get_field_encryption() -> FieldEncryption:
    global _fe
    if _fe is None:
        _fe = FieldEncryption.from_env()
    return _fe


def encrypt_field(value: str) -> str:
    """Shortcut: encrypt a DB field value."""
    return get_field_encryption().encrypt(value)


def decrypt_field(value: str) -> str:
    """Shortcut: decrypt a DB field value. Passthrough if not encrypted."""
    return get_field_encryption().decrypt(value)
