"""Trade service patch stub."""
from __future__ import annotations


class TradeServicePatch:
    """Stub for trade service patch functionality."""

    async def patch_order(self, order_id: str, updates: dict) -> dict:
        return {"order_id": order_id, "status": "patched", **updates}

    async def cancel_order(self, order_id: str, reason: str = "") -> dict:
        return {"order_id": order_id, "status": "cancelled", "reason": reason}
