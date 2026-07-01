"""Auto-repaired placeholder - original had syntax errors."""
from __future__ import annotations
from fastapi import APIRouter, Depends

# TODO: Original file had syntax errors (base64 content) that could not be decoded.
# File: backend/api/routes/dashboard.py

router = APIRouter(prefix='/dashboard', tags=['dashboard'])

@router.get('/summary')
async def get_dashboard_summary():
    return {'status': 'ok', 'message': 'Dashboard stub - needs manual repair'}
