"""signal_service.py -- Phase P Fixes P-7a/b/c/d/e."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from ..core.logger import get_logger
from ..core.enums import SignalStatus
from ..database import db
from .audit_service import audit_service, AuditAction

logger = get_logger("signal_service")

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class SignalService:
    async def get_signals(
        self, user_id: str, status: Optional[str] = None,
        symbol: Optional[str] = None, direction: Optional[str] = None,
        min_score: Optional[int] = None, include_expired: bool = False,
        limit: int = 50, offset: int = 0,
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = {"user_id": user_id}
        if status:
            filters["status"] = status
        if symbol:
            filters["symbol"] = symbol.strip().upper()
        if direction:
            filters["direction"] = direction.strip().upper()
        try:
            signals = await db.select_many(
                table="signals", filters=filters, limit=limit,
                offset=offset, order_by="created_at", ascending=False,
            ) or []
            if min_score is not None:
                signals = [s for s in signals if (s.get("score") or 0) >= min_score]
            if not include_expired:
                now_iso = _utcnow().isoformat()
                signals = [s for s in signals
                           if not s.get("expires_at") or s["expires_at"] > now_iso]
            return {"signals": signals, "total": len(signals),
                    "limit": limit, "offset": offset}
        except Exception as exc:
            logger.error("[SignalService.get_signals] error: %s", exc)
            return {"signals": [], "total": 0, "limit": limit,
                    "offset": offset, "error": str(exc)}

    async def get_signal_by_id(self, signal_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            rows = await db.select_many(
                table="signals",
                filters={"id": signal_id, "user_id": user_id},
                limit=1,
            )
            return rows[0] if rows else None
        except Exception as exc:
            logger.error("[SignalService.get_signal_by_id] error: %s", exc)
            return None

    async def create_signal(
        self, user_id: str, symbol: str, direction: str,
        entry_price: float, stop_loss: float, take_profit: float,
        score: int = 0, metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        signal = {
            "id": str(uuid.uuid4()), "user_id": user_id,
            "symbol": symbol.upper(), "direction": direction.upper(),
            "entry_price": entry_price, "stop_loss": stop_loss,
            "take_profit": take_profit, "score": score,
            "status": SignalStatus.PENDING.value,
            "metadata": metadata or {}, "created_at": _utcnow().isoformat(),
        }
        try:
            result = await db.insert("signals", signal)
            await audit_service.log(
                action=AuditAction.SIGNAL_CREATED, user_id=user_id,
                resource_id=signal["id"],
                details={"symbol": symbol, "direction": direction},
            )
            return result or signal
        except Exception as exc:
            logger.error("[SignalService.create_signal] error: %s", exc)
            raise

    async def update_signal_status(self, signal_id: str, user_id: str, status: str) -> bool:
        try:
            existing = await self.get_signal_by_id(signal_id, user_id)
            if not existing:
                return False
            await db.update(
                table="signals",
                filters={"id": signal_id, "user_id": user_id},
                data={"status": status, "updated_at": _utcnow().isoformat()},
            )
            return True
        except Exception as exc:
            logger.error("[SignalService.update_signal_status] error: %s", exc)
            return False

signal_service = SignalService()
