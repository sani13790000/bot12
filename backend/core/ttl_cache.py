"""backend/core/ttl_cache.py — shared TTL + LRU cache for permission checks.

Extracted from the previously duplicated ``_PermCache`` implementations in
``core/permissions.py`` and ``core/rbac.py`` (identical logic, differing only
in default capacity/TTL constants).
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional, Tuple

DEFAULT_TTL_SEC = 60
DEFAULT_MAX_SIZE = 2048


class TTLPermissionCache:
    """LRU cache with per-entry TTL, mapping string keys to booleans.

    Keys are expected to be namespaced as ``"{user_id}:..."`` so that
    :meth:`invalidate_user` can drop every entry belonging to a single user.
    """

    def __init__(self, max_size: int = DEFAULT_MAX_SIZE, ttl: int = DEFAULT_TTL_SEC) -> None:
        self._store: OrderedDict[str, Tuple[bool, datetime]] = OrderedDict()
        self._max = max_size
        self._ttl = ttl

    def get(self, key: str) -> Optional[bool]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if (datetime.now(timezone.utc) - ts).total_seconds() > self._ttl:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: bool) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, datetime.now(timezone.utc))
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def invalidate_user(self, user_id: str) -> None:
        drop = [k for k in self._store if k.startswith(f"{user_id}:")]
        for k in drop:
            self._store.pop(k, None)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
