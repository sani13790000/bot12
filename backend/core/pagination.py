"""backend/core/pagination.py — Phase 12
P12-FIX-PAG-1: Depends(offset_pagination) در همه routes
P12-FIX-PAG-2: limit max 100
P12-FIX-PAG-3: cursor-based برای high-volume
P12-FIX-PAG-4: standard envelope
"""
from __future__ import annotations
import base64, json, time
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Optional, TypeVar
from fastapi import Query, HTTPException
from .error_codes import EC, api_error

T = TypeVar("T")
_MAX_LIMIT     = 100
_DEFAULT_LIMIT = 50
_MAX_OFFSET    = 10_000


@dataclass
class OffsetPage:
    limit:  int
    offset: int

    @property
    def next_offset(self) -> int:
        return self.offset + self.limit


@dataclass
class CursorPage:
    limit:  int
    cursor: Optional[str]

    def decode_cursor(self) -> Optional[Dict[str, Any]]:
        if not self.cursor:
            return None
        try:
            raw = base64.urlsafe_b64decode(self.cursor + "==")
            return json.loads(raw)
        except Exception:
            raise HTTPException(
                status_code=422,
                detail=api_error(EC.VALIDATION_PAGINATION,
                                 detail="Invalid cursor format").to_response(),
            )

    @staticmethod
    def encode_cursor(ts: float, row_id: str) -> str:
        raw = json.dumps({"ts": ts, "id": row_id}).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@dataclass
class PagedResponse(Generic[T]):
    items:       List[T]
    total:       Optional[int]  = None
    limit:       int            = _DEFAULT_LIMIT
    offset:      int            = 0
    next_cursor: Optional[str]  = None
    has_more:    bool           = False

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"items": self.items, "limit": self.limit, "has_more": self.has_more}
        if self.total is not None:
            out["total"] = self.total
        if self.offset:
            out["offset"] = self.offset
        if self.next_cursor:
            out["next_cursor"] = self.next_cursor
        return out


def offset_pagination(
    limit:  int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0, le=_MAX_OFFSET),
) -> OffsetPage:
    return OffsetPage(limit=limit, offset=offset)


def cursor_pagination(
    limit:  int           = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    cursor: Optional[str] = Query(default=None),
) -> CursorPage:
    return CursorPage(limit=limit, cursor=cursor)


def build_paged_response(
    items: List[Any],
    page:  OffsetPage,
    total: Optional[int] = None,
) -> Dict[str, Any]:
    has_more = len(items) == page.limit
    return PagedResponse(
        items=items, total=total, limit=page.limit,
        offset=page.offset, has_more=has_more,
    ).to_dict()


def build_cursor_response(
    items:    List[Dict[str, Any]],
    page:     CursorPage,
    ts_field: str = "created_at",
    id_field: str = "id",
) -> Dict[str, Any]:
    has_more    = len(items) == page.limit
    next_cursor = None
    if has_more and items:
        last = items[-1]
        ts   = last.get(ts_field, time.time())
        rid  = last.get(id_field, "")
        next_cursor = CursorPage.encode_cursor(
            float(ts) if isinstance(ts, (int, float)) else time.time(), str(rid)
        )
    resp = PagedResponse(
        items=items, limit=page.limit,
        next_cursor=next_cursor, has_more=has_more,
    ).to_dict()
    if not has_more:
        resp.pop("next_cursor", None)
    return resp
