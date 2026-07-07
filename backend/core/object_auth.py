"""backend/core/object_auth.py — Phase 12
P12-FIX-OLA-1: owner_id == current_user.sub required
P12-FIX-OLA-2: admin bypass
P12-FIX-OLA-3: hoist OLA to dependency
P12-FIX-OLA-4: deny logging
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from .error_codes import EC, api_error

_ADMIN_ROLES = frozenset({"admin", "super_admin", "support"})
_WRITE_ADMIN_ROLES = frozenset({"admin", "super_admin"})
_log = logging.getLogger("api.ola")


def check_resource_owner(
    resource_owner_id: str,
    current_user: Dict[str, Any],
    allow_admin: bool = True,
    require_write_admin: bool = False,
) -> None:
    user_id = current_user.get("sub") or current_user.get("user_id", "")
    role = current_user.get("role", "")
    if allow_admin:
        if require_write_admin and role in _WRITE_ADMIN_ROLES:
            return
        if not require_write_admin and role in _ADMIN_ROLES:
            return
    if str(resource_owner_id) == str(user_id):
        return
    _log.warning("OLA_DENIED user=%s attempted resource owned by %s", user_id, resource_owner_id)
    err = api_error(EC.PERM_OWNER_REQUIRED)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=err.to_response())


def assert_owns(
    resource: Optional[Dict[str, Any]],
    user: Dict[str, Any],
) -> Dict[str, Any]:
    if resource is None:
        raise HTTPException(status_code=404, detail=api_error(EC.NOT_FOUND).to_response())
    check_resource_owner(resource.get("user_id", resource.get("owner_id", "")), user)
    return resource


def assert_owns_or_admin(
    resource: Optional[Dict[str, Any]],
    user: Dict[str, Any],
) -> Dict[str, Any]:
    if resource is None:
        raise HTTPException(status_code=404, detail=api_error(EC.NOT_FOUND).to_response())
    check_resource_owner(
        resource.get("user_id", resource.get("owner_id", "")), user, allow_admin=True
    )
    return resource


def require_self_or_admin(user_id_param: str, current_user: Dict[str, Any]) -> None:
    role = current_user.get("role", "")
    sub = current_user.get("sub", "")
    if role in _WRITE_ADMIN_ROLES:
        return
    if str(user_id_param) == str(sub):
        return
    raise HTTPException(status_code=403, detail=api_error(EC.PERM_OWNER_REQUIRED).to_response())
