"""backend/license/dependency.py
Phase 6 FastAPI dependencies for license enforcement

Usage:
    from ..license.dependency import require_license, require_feature, require_plan

    @router.get('/signals')
    async def get_signals(
        lic: LicenseCheckResult = Depends(require_feature('signals_read')),
    ):
        ...
"""
