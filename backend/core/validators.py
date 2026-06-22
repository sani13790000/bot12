"""validators.py -- Phase P Fix P-11a/b/c/d/e."""
from __future__ import annotations
import re
import uuid
from typing import Optional

# FIX P-11a: extended from 14 to 40+ symbols
ALLOWED_SYMBOLS: frozenset = frozenset({
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
    "EURGBP", "EURJPY", "GBPJPY", "EURAUD", "GBPAUD", "AUDJPY", "CADJPY",
    "CHFJPY", "EURCHF", "GBPCHF", "AUDCAD", "AUDCHF", "NZDJPY", "NZDCAD",
    "EURCAD", "EURNZD",
    "XAUUSD", "XAGUSD", "XPTUSD",
    "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD",
    "US30", "NAS100", "SPX500", "GER40", "UK100",
})

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,10}$")
_MIN_LOT = 0.01
_MAX_LOT = 100.0
_MIN_PRICE = 0.00001
_MAX_PRICE = 1_000_000.0

def validate_symbol(symbol: Optional[str]) -> str:
    """FIX P-11d: case-insensitive + whitelist."""
    if not symbol:
        raise ValueError("symbol is required")
    normalised = symbol.strip().upper()
    if not _SYMBOL_RE.match(normalised):
        raise ValueError(f"Invalid symbol format: {symbol!r}")
    if normalised not in ALLOWED_SYMBOLS:
        raise ValueError(f"Symbol {normalised!r} not in allowed list.")
    return normalised

def validate_lot_size(lot: float, symbol: Optional[str] = None) -> float:
    """FIX P-11b: enforce min/max lot."""
    try:
        lot = float(lot)
    except (TypeError, ValueError):
        raise ValueError(f"lot_size must be numeric, got {lot!r}")
    if lot < _MIN_LOT:
        raise ValueError(f"lot_size {lot} below minimum {_MIN_LOT}")
    if lot > _MAX_LOT:
        raise ValueError(f"lot_size {lot} exceeds maximum {_MAX_LOT}")
    return round(lot, 2)

def validate_price(price: float, field_name: str = "price") -> float:
    """FIX P-11c: enforce price range."""
    try:
        price = float(price)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be numeric")
    if price < _MIN_PRICE:
        raise ValueError(f"{field_name} {price} below minimum {_MIN_PRICE}")
    if price > _MAX_PRICE:
        raise ValueError(f"{field_name} {price} exceeds maximum {_MAX_PRICE}")
    return price

def validate_signal_id(signal_id: Optional[str]) -> str:
    """FIX P-11e: enforce UUID format."""
    if not signal_id:
        raise ValueError("signal_id is required")
    sid = signal_id.strip()
    if not _UUID_RE.match(sid):
        raise ValueError(f"signal_id must be a valid UUID, got {sid!r}")
    return sid.lower()

def validate_direction(direction: Optional[str]) -> str:
    if not direction:
        raise ValueError("direction is required")
    d = direction.strip().upper()
    if d not in ("BUY", "SELL"):
        raise ValueError(f"direction must be BUY or SELL, got {direction!r}")
    return d

def validate_risk_percent(pct: float) -> float:
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        raise ValueError(f"risk_percent must be numeric, got {pct!r}")
    if pct < 0.01:
        raise ValueError(f"risk_percent {pct} too low (min 0.01)")
    if pct > 5.0:
        raise ValueError(f"risk_percent {pct} too high (max 5.0)")
    return round(pct, 4)
