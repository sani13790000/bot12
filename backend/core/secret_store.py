"""backend/core/secret_store.py — AES-GCM Secret Store"""
from __future__ import annotations
import base64, os, secrets, time
from dataclasses import dataclass, field
from typing import Any

class DecryptionError(Exception): pass
class SecretNotFoundError(KeyError): pass

def _derive_key(password: bytes, salt: bytes) -> bytes:
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", password, salt, 260000, dklen=32)

def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce + ct

def _aes_gcm_decrypt(key: bytes, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        return AESGCM(key).decrypt(data[:12], data[12:], None)
    except Exception as e:
        raise DecryptionError(str(e)) from e

@dataclass
class EncryptedEnvelope:
    salt: bytes
    encrypted_dek: bytes
    encrypted_payload: bytes

    def to_bytes(self) -> bytes:
        import struct
        def enc(b): return struct.pack(">I", len(b)) + b
        return enc(self.salt) + enc(self.encrypted_dek) + enc(self.encrypted_payload)

    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedEnvelope":
        import struct
        pos = 0
        fields = []
        for _ in range(3):
            size = struct.unpack_from(">I", data, pos)[0]; pos += 4
            fields.append(data[pos:pos+size]); pos += size
        return cls(*fields)

def envelope_encrypt(master_key: bytes, plaintext: bytes) -> bytes:
    salt = secrets.token_bytes(32)
    kek = _derive_key(master_key, salt)
    dek = secrets.token_bytes(32)
    enc_dek = _aes_gcm_encrypt(kek, dek)
    enc_payload = _aes_gcm_encrypt(dek, plaintext)
    return EncryptedEnvelope(salt, enc_dek, enc_payload).to_bytes()

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
class _Record:
    ciphertext: bytes
    created_at: float = field(default_factory=time.time)
    rotated_at: float | None = None
    access_count: int = 0

class SecretStore:
    def __init__(self, master_password: str) -> None:
        self._master = master_password.encode()
        self._store: dict[str, _Record] = {}
        self._audit: list[dict] = []

    def put(self, name: str, value: str) -> None:
        ct = envelope_encrypt(self._master, value.encode())
        self._store[name] = _Record(ciphertext=ct)
        self._audit.append({"action": "put", "name": name, "ts": time.time()})

    def get(self, name: str) -> str:
        if name not in self._store:
            raise SecretNotFoundError(name)
        rec = self._store[name]
        rec.access_count += 1
        self._audit.append({"action": "get", "name": name, "ts": time.time()})
        return envelope_decrypt(self._master, rec.ciphertext).decode()

    def rotate(self, name: str, new_value: str) -> None:
        if name not in self._store:
            raise SecretNotFoundError(name)
        ct = envelope_encrypt(self._master, new_value.encode())
        self._store[name].ciphertext = ct
        self._store[name].rotated_at = time.time()
        self._audit.append({"action": "rotate", "name": name, "ts": time.time()})

    def delete(self, name: str) -> None:
        self._store.pop(name, None)
        self._audit.append({"action": "delete", "name": name, "ts": time.time()})

    def exists(self, name: str) -> bool:
        return name in self._store

    def list_names(self) -> list[str]:
        return list(self._store.keys())

    def audit_log(self) -> list[dict]:
        return list(self._audit)

_store: SecretStore | None = None

def get_secret_store() -> SecretStore:
    global _store
    if _store is None:
        master = os.environ.get("SECRETS_MASTER_KEY", "default-dev-master-key-32-bytes!")
        _store = SecretStore(master)
        for k, v in os.environ.items():
            if k in ("JWT_SECRET_KEY", "MT5_PASSWORD", "SUPABASE_SERVICE_KEY"):
                _store.put(k, v)
    return _store

__all__ = [
    "DecryptionError", "SecretNotFoundError", "SecretStore",
    "EncryptedEnvelope", "_aes_gcm_encrypt", "_aes_gcm_decrypt",
    "_derive_key", "envelope_encrypt", "envelope_decrypt", "get_secret_store"
]
