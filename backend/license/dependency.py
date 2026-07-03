"""
Module: dependency
Path: backend/license/dependency.py
Note: License dependency injection stub.
"""
from __future__ import annotations
from typing import Optional


def get_license_engine():
    """Get the license engine instance."""
    from backend.license.engine import LicenseEngine
    return LicenseEngine()
