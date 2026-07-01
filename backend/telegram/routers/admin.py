"""
backend/telegram/routers/admin.py
Galaxy Vast AI — Telegram Admin Router
NOTE: Auto-repaired stub.
"""
from __future__ import annotations
import logging

try:
    from aiogram import Router
    admin_router = Router()
except ImportError:
    admin_router = None

_LOG = logging.getLogger(__name__)


def setup_admin_router():
    """Setup admin router with handlers."""
    return admin_router
