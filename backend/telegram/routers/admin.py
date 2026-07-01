"""
backend/telegram/routers/admin.py — repair stub.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter
router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)
__all__ = ["router"]
