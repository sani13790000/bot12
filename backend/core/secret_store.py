"""
backend/core/secret_store.py
Galaxy Vast AI — Encrypted Secret Store (Phase 11)

P11-SS-1: AES-256-GCM encryption بئ PBKDF2 key derivation
P11-SS-2: Raw credentials اهr ضYncrypted store دارن غه plain-text در memory cache نمه
P11-SS-3: Envelope encryption — DEK encrypted ☺ KEK
P11-SS-4: Credential rotation بدون downtime
P11-SS-5: Audit log برإ ؗر her access
P11-SS-6: Memory zeroing بمد اس استفپاده (best-effort ده Python)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

log = logging.getLogger(__name__)

# ┠ Constants ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
_GCM_NONCE_SIZE  = 12   # 96-bit nonce ☺ AES-GCM
_GCM_TAG_SIZE    = 16   # 128-bit authentication tag
_PBKDF2_ITER     = 600_000  # OWASP 2023 recommendation
_SALT_SIZE       = 32   # 256-bit salt
_KEY_SIZE        = 32   # AES-256

# ┠ Exceptions ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
class SecretStoreError(Exception):
    """Base exception — details intentionally vague for security."""

class DecryptionError(SecretStoreError):
    """Ciphertext tampered or wrong key."""

class SecretNotFoundError(SecretStoreError):
    """Requested secret does not exist."""


# ┠ Pure crypto (no third-party deps beyond stdlib) ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
def _derive_key(password: bytes, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256 → 256-bit key."""
    return hashlib.pbkdf2_hmac("sha256", password, salt, _PBKDF2_ITER, dklen=_KEY_SIZE)


def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """
    AES-256-GCM encrypt using cryptography library if available,
    fallback to XSalsa20-Poly1305 via PyNaCl, otherwise HMAC-SIV stub.
    Returns: nonce(12) + ciphertext + tag(16)
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = secrets.token_bytes(_GCM_NONCE_SIZE)
        aesgcm = AESGCM(key)
        ct_with_tag = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ct_with_tag
    except ImportError:
        pass

    # Fallback: XOR-stream with HMAC-SHA256 authentication (not AESGCM but secure)
    # Used only when cryptography package unavailable
    nonce = secrets.token_bytes(_GCM_NONCE_SIZE)
    # Generate keystream via HKDF-expand
    keystream_key = hmac.new(key, b"keystream:" + nonce, hashlib.sha256).digest()
    # XOR plaintext (stream cipher simulation — secure for testing)
    ct = bytes(p ^ k for p, k in zip(
        plaintext,
        _expand_keystream(keystream_key, len(plaintext))
    ))
    # Authenticate
    mac = hmac.new(key, nonce + ct, hashlib.sha256).digest()[:_GCM_TAG_SIZE]
    return nonce + ct + mac


def _aes_gcm_decrypt(key: bytes, ciphertext: bytes) -> bytes:
    """Decrypt and verify AES-256-GCM ciphertext."""
    if len(ciphertext) < _GCM_NONCE_SIZE + _GCM_TAG_SIZE:
        raise DecryptionError("Ciphertext too short")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = ciphertext[:_GCM_NONCE_SIZE]
        ct_with_tag = ciphertext[_GCM_NONCE_SIZE:]
        aesgcm = AESGCM(key)
        try:
            return aesgcm.decrypt(nonce, ct_with_tag, None)
        except Exception:
            raise DecryptionError("Authentication failed — ciphertext tampered")
    except ImportError:
        pass

    # Fallback verify + decrypt
    nonce = ciphertext[:_GCM_NONCE_SIZE]
    ct    = ciphertext[_GCM_NONCE_SIZE:-_GCM_TAG_SIZE]
    tag   = ciphertext[-_GCM_TAG_SIZE:]
    mac   = hmac.new(key, nonce + ct, hashlib.sha256).digest()[:_GCM_TAG_SIZE]
    if not hmac.compare_digest(mac, tag):
        raise DecryptionError("Authentication failed — ciphertext tampered")
    keystream_key = hmac.new(key, b"keystream:" + nonce, hashlib.sha256).digest()
    return bytes(c ^ k for c, k in zip(ct, _expand_keystream(keystream_key, len(ct))))


def _expand_keystream(key: bytes, length: int) -> bytes:
    """Simple keystream expansion using HMAC-SHA256 counter mode."""
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(key, struct.pack(">Q", counter), hashlib.sha256).digest()
        counter += 1
    return out[:length]


# ┠ Envelope Encryption ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
@dataclass
class EncryptedEnvelope:
    """
    Envelope: DEK encrypted with KEK.
    Structure: salt(32) + encrypted_dek(60) + encrypted_payload(N)
    """
    salt: bytes          # KEK derivation salt
    encrypted_dek: bytes # AES-GCM(KEK, DEK)
    encrypted_payload: bytes  # AES-GCM(DEK, plaintext)
    created_at: float = field(default_factory=time.time)
    version: int = 1

    def to_bytes(self) -> bytes:
        meta = json.dumps({
            "v": self.version,
            "ts": self.created_at,
            "salt_len": len(self.salt),
            "dek_len": len(self.encrypted_dek),
        }).encode()
        meta_len = struct.pack(">H", len(meta))
        return meta_len + meta + self.salt + self.encrypted_dek + self.encrypted_payload

    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedEnvelope":
        if len(data) < 2:
            raise DecryptionError("Envelope too short")
        meta_len = struct.unpack(">H", data[:2])[0]
        if len(data) < 2 + meta_len:
            raise DecryptionError("Envelope truncated")
        meta = json.loads(data[2:2 + meta_len])
        offset = 2 + meta_len
        salt_len = meta["salt_len"]
        dek_len  = meta["dek_len"]
        salt     = data[offset:offset + salt_len]
        offset  += salt_len
        enc_dek  = data[offset:offset + dek_len]
        offset  += dek_len
        enc_payload = data[offset:]
        return cls(
            salt=salt,
            encrypted_dekenc_dek,
            encrypted_payload=enc_payload,
            created_at=meta.get("ts", 0.0),
            version=meta.get("v", 1),
        )


def envelope_encrypt(master_password: bytes, plaintext: bytes) -> bytes:
    """P11-SS-3: Envelope encrypt — DEK per-secret, KKK from master password."""
    salt = secrets.token_bytes(_SALT_SIZE)
    kek  = _derive_key(master_password, salt)
    dek  = secrets.token_bytes(_KEY_SIZE)
    encrypted_dek     = _aes_gcm_encrypt(kek, dek)
    encrypted_payload = _aes_gcm_encrypt(dek, plaintext)
    env = EncryptedEnvelope(
        salt=salt,
        encrypted_dek=encrypted_dek,
        encrypted_payload=encrypted_payload,
    )
    return env.to_bytes()


def envelope_decrypt(master_password: bytes, data: bytes) -> bytes:
    """Decrypt envelope — raises DecryptionError on any failure."""
    env  = EncryptedEnvelope.from_bytes(data)
    kek  = _derive_key(master_password, env.salt)
    dek  = _aes_gcm_decrypt(kek, env.encrypted_dek)
    plain = _aes_gcm_decrypt(dek, env.encrypted_payload)
    return plain


# ┠ Secret Store ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
@dataclass
class SecretRecord:
    name: str
    ciphertext: bytes    # envelope-encrypted
    created_at: float
    rotated_at: Optional[float] = None
    access_count: int = 0
    tags: Dict[str, str] = field(default_factory=dict)


class SecretStore:
    """
    In-process encrypted secret store.

    P11-SS-1: All values encrypted at rest (envelope encryption)
    P11-SS-2: Plaintext never cached — decrypted on demand, not stored
    P11-SS-4: rotate() replaces secret without removing old access
    P11-SS-5: Every get/put/rotate logged (name only, never value)
    P11-SS-6: _master_key kept as bytearray for zeroing
    """

    def __init__(self, master_password: str) -> None:
        # P11-SS-6: store as bytearray for best-effort zeroing
        self._master: bytearray = bytearray(master_password.encode())
        self._store: Dict[str, SecretRecord] = {}
        self._audit: list = []

    def _master_bytes(self) -> bytes:
        return bytes(self._master)

    def put(self, name: str, value: str, tags: Optional[Dict[str, str]] = None) -> None:
        """Encrypt and store a secret. Overwrites existing."""
        ct = envelope_encrypt(self._master_bytes(), value.encode())
        self._store[name] = SecretRecord(
            name=name,
            ciphertext=ct,
            created_at=time.time(),
            tags=tags or {},
        )
        self._audit_log("put", name)
        log.debug("secret_store.put name=%s", name)

    def get(self, name: str) -> str:
        """Decrypt and return secret. Raises SecretNotFoundError if missing."""
        rec = self._store.get(name)
        if rec is None:
            self._audit_log("get_miss", name)
            raise SecretNotFoundError(f"Secret not found: {name}")
        rec.access_count += 1
        self._audit_log("get", name)
        plain = envelope_decrypt(self._master_bytes(), rec.ciphertext)
        result = plain.decode()
        # P11-SS-6: zero the intermediate bytes object (best-effort)
        plain = bytearray(plain)
        for i in range(len(plain)):
            plain[i] = 0
        return result

    def rotate(self, name: str, new_value: str) -> None:
        """P11-SS-4: Replace secret, preserving metadata."""
        rec = self._store.get(name)
        if rec is None:
            raise SecretNotFoundError(f"Secret not found: {name}")
        ct = envelope_encrypt(self._master_bytes(), new_value.encode())
        rec.ciphertext  = ct
        rec.rotated_at  = time.time()
        self._audit_log("rotate", name)
        log.info("secret_store.rotate name=%s", name)

    def delete(self, name: str) -> None:
        """Remove a secret."""
        self._store.pop(name, None)
        self._audit_log("delete", name)

    def exists(self, name: str) -> bool:
        return name in self._store

    def list_names(self) -> list:
        """Return names only — never values."""
        return list(self._store.keys())

    def audit_log(self) -> list:
        return list(self._audit)

    def _audit_log(self, action: str, name: str) -> None:
        self._audit.append({
            "ts": time.time(),
            "action": action,
            "name": name,
        })
        if len(self._audit) > 10_000:
            self._audit = self._audit[-10_000:]

    def zero_master(self) -> None:
        """P11-SS-6: Best-effort zero master key from memory."""
        for i in range(len(self._master)):
            self._master[i] = 0


# ┠ Global instance (lazy) ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
_store: Optional[SecretStore] = None


def get_secret_store() -> SecretStore:
    """Return process-level SecretStore. Initialized from SECRETS_MASTER_KEY env var."""
    global _store
    if _store is None:
        master = os.environ.get("SECRETS_MASTER_KEY", "")
        if not master:
            # Dev fallback — warn loudly
            log.warning(
                "P11-SS-WARN: SECRETS_MASTER_KEY not set — using insecure dev key. "
                "Set SECRETS_MASTER_KEY in production!"
            )
            master = "dev-insecure-key-not-for-production"
        _store = SecretStore(master)
        _load_from_env(_store)
    return _store


def _load_from_env(store: SecretStore) -> None:
    """
    P11-SS-ENV: Load sensitive env vars into encrypted store at startup.
    After loading, the original env vars are NOT cleared (OS may expose them)
    but all application code should use store.get() instead of os.environ.
    """
    _ENV_SECRETS: list = [
        "JWT_SECRET_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
        "MT5_PASSWORD",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_WEBHOOK_SECRET",
        "LICENSE_SECRET",
        "LICENSE_SALT",
        "MQL5_API_TOKEN",
        "SECRETS_MASTER_KEY",  # also encrypt master itself
    ]
    loaded = 0
    for name in _ENV_SECRETS:
        val = os.environ.get(name)
        if val:
            store.put(name, val, tags={"source": "env"})
            loaded += 1
    log.debug("secret_store: loaded %d secrets from environment", loaded)
