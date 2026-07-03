"""
Module: engine
Path: backend/license/engine.py
License validation engine stub.
"""
from __future__ import annotations


class LicenseEngine:
    """License validation engine."""

    def validate(self, key: str) -> bool:
        """Validate a license key."""
        return bool(key)

    def is_valid(self) -> bool:
        """Check if current license is valid."""
        return True
