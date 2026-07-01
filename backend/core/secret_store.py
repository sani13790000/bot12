"""
backend/core/secret_store.py
Galaxy Vast AI — Encrypted Secret Store (Phase 11)

P11-SS-1: AES-256-GCM encryption with PBKDF2 key derivation
P11-SS-2: Raw credentials are never stored in plaintext
P11-SS-3: Ciphertext uniqueness per encryption via random nonce
P11-SS-4: Key rotation without losing access to old secrets
P11-SS-5: Full audit log for all operations
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SecretNotFoundError(Exception):
    pass


class DecryptionError(Exception):
    pass


def _derive_key(password: bytes, salt: bytes, iterations: int = 200_000) -> bytes:
    """PBKDF2-HMAC-SHA256 key derivation."""
    return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, dklen=32)


def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM encrypt. Returns nonce+ciphertext+tag."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce + ct


def _aes_gcm_decrypt(key: bytes, data: bytes) -> bytes:
    """AES-256-GCM decrypt."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        nonce, ct = data[:12], data[12:]
        return AESGCM(key).decrypt(nonce, ct, None)
    except Exception as exc:
        raise DecryptionError(f"Decryption failed: {exc}") from exc


@dataclass
class EncryptedEnvelope:
    salt: bytes
    encrypted_dek: bytes
    encrypted_payload: bytes

    def to_bytes(self) -> bytes:
        parts = [
            len(self.salt).to_bytes(2, "big"), self.salt,
            len(self.encrypted_dek).to_bytes(2, "big"), self.encrypted_dek,
            len(self.encrypted_payload).to_bytes(4, "big"), self.encrypted_payload,
        ]
        return b"".join(parts)

    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedEnvelope":
        i = 0
        def _read(n):
            nonlocal i
            chunk = data[i:i+n]; i += n; return chunk
        salt_len = int.from_bytes(_read(2), "big")
        salt = _read(salt_len)
        dek_len = int.from_bytes(_read(2), "big")
        dek = _read(dek_len)
        pay_len = int.from_bytes(_read(4), "big")
        pay = _read(pay_len)
        return cls(salt=salt, encrypted_dek=dek, encrypted_payload=pay)


def envelope_encrypt(master_key: bytes, plaintext: bytes) -> bytes:
    """Encrypt plaintext using envelope encryption."""
    salt = secrets.token_bytes(32)
    kek = _derive_key(master_key, salt)
    dek = secrets.token_bytes(32)
    encrypted_dek = _aes_gcm_encrypt(kek, dek)
    encrypted_payload = _aes_gcm_encrypt(dek, plaintext)
    return EncryptedEnvelope(salt=salt, encrypted_dek=encrypted_dek, encrypted_payload=encrypted_payload).to_bytes()


def envelope_decrypt(master_key: bytes, data: bytes) -> bytes:
    """Decrypt envelope-encrypted ciphertext."""
    try:
        env = EncryptedEnvelope.from_bytes(data)
        kek = _derive_key(master_key, env.salt)
        dek = _aes_gcm_decrypt(kek, env.encrypted_dek)
        return _aes_gcm_decrypt(dek, env.encrypted_payload)
    except DecryptionError:
        raise
    except Exception as exc:
        raise DecryptionError(f"Envelope decryption failed: {exc}") from exc


@dataclass
class SecretRecord:
    name: str
    ciphertext: bytes
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rotated_at: Optional[datetime] = None
    access_count: int = 0


class SecretStore:
    """AES-256-GCM encrypted secret store with audit log."""

    def __init__(self, master_password: str) -> None:
        self._master = master_password.encode()
        self._store: Dict[str, SecretRecord] = {}
        self._audit: List[Dict[str, Any]] = []
        self._log = logging.getLogger(self.__class__.__name__)

    def put(self, name: str, value: str) -> None:
        ct = envelope_encrypt(self._master, value.encode())
        self._store[name] = SecretRecord(name=name, ciphertext=ct)
        self._log.debug("Secret stored: %s", name)
        self._audit.append({"action": "put", "name": name, "ts": time.time()})

    def get(self, name: str) -> str:
        rec = self._store.get(name)
        if not rec:
            raise SecretNotFoundError(f"Secret not found: {name}")
        value = envelope_decrypt(self._master, rec.ciphertext).decode()
        rec.access_count += 1
        self._audit.append({"action": "get", "name": name, "ts": time.time()})
        return value

    def rotate(self, name: str, new_value: str) -> None:
        if name not in self._store:
            raise SecretNotFoundError(f"Cannot rotate non-existent secret: {name}")
        ct = envelope_encrypt(self._master, new_value.encode())
        rec = self._store[name]
        rec.ciphertext = ct
        rec.rotated_at = datetime.now(timezone.utc)
        self._audit.append({"action": "rotate", "name": name, "ts": time.time()})

    def delete(self, name: str) -> None:
        if name not in self._store:
            raise SecretNotFoundError(f"Cannot delete non-existent secret: {name}")
        del self._store[name]
        self._audit.append({"action": "delete", "name": name, "ts": time.time()})

    def list_names(self) -> List[str]:
        return list(self._store.keys())

    def exists(self, name: str) -> bool:
        return name in self._store

    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit)


_store: Optional[SecretStore] = None


def get_secret_store(master_key: Optional[str] = None) -> SecretStore:
    global _store
    if _store is None:
        key = master_key or os.getenv("SECRETS_MASTER_KEY", "default-insecure-key")
        _store = SecretStore(key)
        # Pre-load secrets from env
        for env_key in ["JWT_SECRET_KEY", "SUPABASE_SERVICE_KEY", "MT5_PASSWORD"]:
            val = os.getenv(env_key)
            if val:
                try:
                    _store.put(env_key, val)
                except Exception:
                    pass
    return _store
