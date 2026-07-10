"""
backend/core/field_encryption.py
Field-level encryption for sensitive data (passwords, API keys, tokens).
"""

import logging
import os
from typing import Any, Optional
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class FieldEncryption:
    """Field-level encryption service."""

    def __init__(self, key: Optional[str] = None):
        """
        Initialize encryption.

        Args:
            key: Encryption key (defaults to ENCRYPTION_KEY env var)
        """
        self.key = key or os.getenv("ENCRYPTION_KEY", "")
        if not self.key:
            logger.warning("[encryption] No encryption key provided - encryption disabled")
            self.cipher = None
        else:
            try:
                self.cipher = Fernet(self.key.encode() if isinstance(self.key, str) else self.key)
            except Exception as e:
                logger.error("[encryption] Failed to initialize cipher: %s", e)
                self.cipher = None

    def encrypt(self, value: str) -> str:
        """
        Encrypt a string value.

        Args:
            value: Value to encrypt

        Returns:
            Encrypted value (or original if encryption disabled)
        """
        if not self.cipher or not value:
            return value

        try:
            encrypted = self.cipher.encrypt(value.encode())
            return encrypted.decode()
        except Exception as exc:
            logger.error("[encryption] Encryption failed: %s", exc)
            return value

    def decrypt(self, value: str) -> str:
        """
        Decrypt a string value.

        Args:
            value: Encrypted value

        Returns:
            Decrypted value (or original if decryption fails)
        """
        if not self.cipher or not value:
            return value

        try:
            decrypted = self.cipher.decrypt(value.encode())
            return decrypted.decode()
        except Exception as exc:
            logger.error("[encryption] Decryption failed: %s", exc)
            return value

    def is_encrypted(self, value: str) -> bool:
        """
        Check if value appears to be encrypted.

        Args:
            value: Value to check

        Returns:
            True if value looks encrypted
        """
        if not value:
            return False
        try:
            return value.startswith('gAAAAAA')
        except Exception:
            return False


# Global instance
_encryption: Optional[FieldEncryption] = None


def get_encryption() -> FieldEncryption:
    """Get or create global encryption instance."""
    global _encryption
    if _encryption is None:
        _encryption = FieldEncryption()
    return _encryption
