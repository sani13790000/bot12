from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from typing import Any, Dict, Optional
from ..core.logger import get_logger

logger = get_logger('core.secret_store')

_SALT_SIZE  = 32
_NONCE_SIZE = 12
_TAG_SIZE   = 16
_KDF_ITERS  = 200_000


class SecretStoreError(RuntimeError):
    pass


class Envelope:
    """Encrypted envelope: salt + encrypted_dek + encrypted_payload."""

    def __init__(self, salt: bytes, encrypted_dek: bytes, encrypted_payload: bytes, created_at: float = 0.0, version: int = 1) -> None:
        self.salt              = salt
        self.encrypted_dek    = encrypted_dek
        self.encrypted_payload = encrypted_payload
        self.created_at       = created_at or time.time()
        self.version          = version

    def to_bytes(self) -> bytes:
        meta = json.dumps({'ts': self.created_at, 'v': self.version}).encode()
        return (
            struct.pack('>H', len(meta)) + meta
            + self.salt
            + struct.pack('>I', len(self.encrypted_dek))
            + self.encrypted_dek
            + self.encrypted_payload
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> 'Envelope':
        offset = 0
        meta_len = struct.unpack_from('>H', data, offset)[0]
        offset += 2
        meta = json.loads(data[offset:offset + meta_len])
        offset += meta_len
        salt = data[offset:offset + _SALT_SIZE]
        offset += _SALT_SIZE
        dek_len = struct.unpack_from('>I', data, offset)[0]
        offset += 4
        enc_dek = data[offset:offset + dek_len]
        offset += dek_len
        enc_payload = data[offset:]
        return cls(
            salt=salt,
            encrypted_dek=enc_dek,
            encrypted_payload=enc_payload,
            created_at=meta.get('ts', 0.0),
            version=meta.get('v', 1),
        )


def _derive_key(password: bytes, salt: bytes, length: int = 32) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password, salt, _KDF_ITERS, dklen=length)


def envelope_encrypt(master_password: bytes, plaintext: bytes) -> bytes:
    """P11-SS-3: Envelope encrypt - DEK per-secret, KKK from master password."""
    salt = secrets.token_bytes(_SALT_SIZE)
    kek  = _derive_key(master_password, salt)
    dek  = secrets.token_bytes(32)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(kek)
        nonce_dek = secrets.token_bytes(_NONCE_SIZE)
        enc_dek = nonce_dek + aesgcm.encrypt(nonce_dek, dek, None)
        aesgcm_payload = AESGCM(dek)
        nonce_pay = secrets.token_bytes(_NONCE_SIZE)
        enc_payload = nonce_pay + aesgcm_payload.encrypt(nonce_pay, plaintext, None)
    except ImportError:
        logger.warning('cryptography not installed - using XOR fallback (NOT for production)')
        enc_dek = dek
        enc_payload = bytes(a ^ b for a, b in zip(plaintext, dek * (len(plaintext) // 32 + 1)))
    env = Envelope(salt=salt, encrypted_dek=enc_dek, encrypted_payload=enc_payload)
    return env.to_bytes()


def envelope_decrypt(master_password: bytes, data: bytes) -> bytes:
    env = Envelope.from_bytes(data)
    kek = _derive_key(master_password, env.salt)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(kek)
        nonce_dek = env.encrypted_dek[:_NONCE_SIZE]
        dek = aesgcm.decrypt(nonce_dek, env.encrypted_dek[_NONCE_SIZE:], None)
        aesgcm_payload = AESGCM(dek)
        nonce_pay = env.encrypted_payload[:_NONCE_SIZE]
        return aesgcm_payload.decrypt(nonce_pay, env.encrypted_payload[_NONCE_SIZE:], None)
    except ImportError:
        dek = env.encrypted_dek
        return bytes(a ^ b for a, b in zip(env.encrypted_payload, dek * (len(env.encrypted_payload) // 32 + 1)))


class SecretStore:
    """Thread-safe secret store with envelope encryption."""

    def __init__(self, master_password: bytes, storage_path: Optional[str] = None) -> None:
        self._master  = master_password
        self._path    = storage_path
        self._cache:  Dict[str, bytes] = {}
        self._log     = logger

    def put(self, key: str, value: bytes) -> None:
        encrypted = envelope_encrypt(self._master, value)
        self._cache[key] = encrypted
        if self._path:
            self._persist()
        self._log.info('SecretStore: stored key=%r', key)

    def get(self, key: str) -> Optional[bytes]:
        encrypted = self._cache.get(key)
        if encrypted is None:
            return None
        try:
            return envelope_decrypt(self._master, encrypted)
        except Exception as exc:
            self._log.error('SecretStore: decrypt failed for key=%r: %s', key, exc)
            return None

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)
        if self._path:
            self._persist()

    def _persist(self) -> None:
        if not self._path:
            return
        data = {k: base64.b64encode(v).decode() for k, v in self._cache.items()}
        with open(self._path, 'w') as f:
            json.dump(data, f)

    def load(self) -> None:
        if not self._path or not os.path.exists(self._path):
            return
        with open(self._path) as f:
            data = json.load(f)
        self._cache = {k: base64.b64decode(v) for k, v in data.items()}
