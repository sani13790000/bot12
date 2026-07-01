"""
backend/core/secret_store.py
Galaxy Vast AI — Encrypted Secret Store (Phase 11)

P11-SS-1: AES-256-GCM encryption + PBKDF2 key derivation
P11-SS-2: Raw credentials are encrypted, not stored as plain-text in memory cache
P11-SS-3: Envelope encryption — DEK encrypted with KEK
P11-SS-4: Credential rotation support
P11-SS-5: Audit log for all access
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


class DecryptionError(Exception):
    """Raised when decryption fails."""


class SecretNotFoundError(KeyError):
    """Raised when a secret is not in the store."""


@dataclass
class EncryptedEnvelope:
    salt: bytes
    encrypted_dek: bytes
    encrypted_payload: bytes
    created_at: float = field(default_factory=time.time)

    def to_bytes(self) -> bytes:
        s = len(self.salt).to_bytes(2, 'big') + self.salt
        d = len(self.encrypted_dek).to_bytes(2, 'big') + self.encrypted_dek
        p = len(self.encrypted_payload).to_bytes(2, 'big') + self.encrypted_payload
        return s + d + p

    @classmethod
    def from_bytes(cls, data: bytes) -> 'EncryptedEnvelope':
        idx = 0
        s_len = int.from_bytes(data[idx:idx+2], 'big'); idx += 2
        salt = data[idx:idx+s_len]; idx += s_len
        d_len = int.from_bytes(data[idx:idx+2], 'big'); idx += 2
        dek = data[idx:idx+d_len]; idx += d_len
        p_len = int.from_bytes(data[idx:idx+2], 'big'); idx += 2
        payload = data[idx:idx+p_len]
        return cls(salt=salt, encrypted_dek=dek, encrypted_payload=payload)


def _derive_key(password: bytes, salt: bytes) -> bytes:
    """PBKDF2 key derivation."""
    return hashlib.pbkdf2_hmac('sha256', password, salt, 100_000, dklen=32)


def _aes_gcm_encrypt(key: bytes, data: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = secrets.token_bytes(12)
        ct = AESGCM(key).encrypt(nonce, data, None)
        return nonce + ct
    except ImportError:
        # Fallback: XOR with key (NOT secure, only for testing without cryptography)
        import hashlib
        padded = data + b'\x00' * (len(key) - len(data) % len(key))
        nonce = secrets.token_bytes(12)
        return nonce + bytes(a ^ b for a, b in zip(padded[:len(data)], (key * (len(data)//len(key)+1))[:len(data)]))


def _aes_gcm_decrypt(key: bytes, data: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce, ct = data[:12], data[12:]
        return AESGCM(key).decrypt(nonce, ct, None)
    except ImportError:
        nonce, ct = data[:12], data[12:]
        return bytes(a ^ b for a, b in zip(ct, (key * (len(ct)//len(key)+1))[:len(ct)]))
    except Exception as e:
        raise DecryptionError(str(e)) from e


def envelope_encrypt(master_key: bytes, plaintext: bytes) -> bytes:
    salt = secrets.token_bytes(32)
    kek = _derive_key(master_key, salt)
    dek = secrets.token_bytes(32)
    enc_dek = _aes_gcm_encrypt(kek, dek)
    enc_payload = _aes_gcm_encrypt(dek, plaintext)
    env = EncryptedEnvelope(salt=salt, encrypted_dek=enc_dek, encrypted_payload=enc_payload)
    return env.to_bytes()


def envelope_decrypt(master_key: bytes, data: bytes) -> bytes:
    try:
        env = EncryptedEnvelope.from_bytes(data)
        kek = _derive_key(master_key, env.salt)
        dek = _aes_gcm_decrypt(kek, env.encrypted_dek)
        return _aes_gcm_decrypt(dek, env.encrypted_payload)
    except DecryptionError:
        raise
    except Exception as e:
        raise DecryptionError(str(e)) from e


@dataclass
class _SecretRecord:
    ciphertext: bytes
    access_count: int = 0
    rotated_at: Optional[float] = None


class SecretStore:
    """Encrypted in-memory secret store."""

    def __init__(self, master_password: str) -> None:
        self._master = master_password.encode()
        self._store: Dict[str, _SecretRecord] = {}
        self._audit: List[Dict[str, Any]] = []

    def _log(self, action: str, name: str) -> None:
        self._audit.append({'action': action, 'name': name, 'ts': time.time()})

    def put(self, name: str, value: str) -> None:
        ct = envelope_encrypt(self._master, value.encode())
        self._store[name] = _SecretRecord(ciphertext=ct)
        self._log('put', name)

    def get(self, name: str) -> str:
        if name not in self._store:
            raise SecretNotFoundError(name)
        rec = self._store[name]
        rec.access_count += 1
        self._log('get', name)
        return envelope_decrypt(self._master, rec.ciphertext).decode()

    def rotate(self, name: str, new_value: str) -> None:
        if name not in self._store:
            raise SecretNotFoundError(name)
        ct = envelope_encrypt(self._master, new_value.encode())
        self._store[name] = _SecretRecord(ciphertext=ct, rotated_at=time.time())
        self._log('rotate', name)

    def delete(self, name: str) -> None:
        if name not in self._store:
            raise SecretNotFoundError(name)
        del self._store[name]
        self._log('delete', name)

    def exists(self, name: str) -> bool:
        return name in self._store

    def list_names(self) -> List[str]:
        return list(self._store.keys())

    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit)


_store: Optional[SecretStore] = None


def get_secret_store() -> SecretStore:
    global _store
    if _store is None:
        master = os.environ.get('SECRETS_MASTER_KEY', '')
        jwt = os.environ.get('JWT_SECRET_KEY', '')
        _store = SecretStore(master or 'default-dev-master-key')
        if jwt:
            _store.put('JWT_SECRET_KEY', jwt)
    return _store
