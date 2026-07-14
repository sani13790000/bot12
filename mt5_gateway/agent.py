"""
Galaxy Vast AI -- MT5 Gateway Agent v2.1.0
فاز O -- bugfix: TRADE_RETCODE_DONE (O-FIX-1) + GATEWAY_API_KEY auth
"""
import os, time, argparse, asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

# --- MT5
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

_mt5_connected = False
_start_time    = time.time()
_order_count   = 0

# --- L-FIX-GW-2: GATEWAY_API_KEY auth
_API_KEY_HEADER = APIKeyHeader(name="X-Gateway-Key", auto_error=False)
_GATEWAY_KEY    = os.environ.get("GATEWAY_API_KEY", "")

def _verify_key(_key: Optional[str] = Security(_API_KEY_HEADER)):
    """API key guard"""
    if not _GATEWAY_KEY:
        return  # dev mode: no key required
    if _key != _GATEWAY_KEY:
        raise HTTPException(status_code=401, detail="X-Gateway-Key namotebaghegh ast")

class OrderRequest(BaseModel):
    symbol:    str
    direction: str          # "buy" | "sell"
    lot:       float        = Field(gt=0)
    sl_pips:   float        = Field(default=50.0, ge=0)
    tp_pips:   float        = Field(default=100.0, ge=0)
    deviation: int          = Field(default=20, ge=0)
    magic:     int          = Field(default=202400)
    signal_id: Optional[str] = None

class CloseRequest(BaseModel):
    ticket: int
    lot:    Optional[float] = None

class ModifyRequest(BaseModel):
    ticket: int
    sl:     Optional[float] = None
    tp:     Optional[float] = None

class CandleRequest(BaseModel):
    symbol:    str
    timeframe: str = Field(default="H1")
    count:     int = Field(default=100, ge=1, le=1000)

def _tf_const(tf: str) -> int:
    if not MT5_AVAILABLE: return 0
    mapping = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
               "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
               "D1": mt5.TIMEFRAME_D1}
    return mapping.get(tf.upper(), mt5.TIMEFRAME_H1)

@asynccontextmanager
async def lifespan(app):
    global _mt5_connected
    if MT5_AVAILABLE:
        login    = int(os.environ.get("MT5_LOGIN", "0"))
        password = os.environ.get("MT5_PASSWORD")
    if not password: raise ValueError("MT5_PASSWORD required in .env")
        server   = os.environ.get("MT5_SERVER", "")
        if login and password and server:
            if mt5.initialize(login=login, password=password, server=server):
                _mt5_connected = True
            else:
                pass  # lifespan dar soorate shekast adame mikonad ta /ping dar dashtras bashad
    yield
    if _mt5_connected and MT5_AVAILABLE:
        mt5.shutdown()

app = FastAPI(title="Galaxy Vast MT5 Gateway", version="2.1.0", lifespan=lifespan,
             docs_url="/docs" if os.environ.get("GATEWAY_ENV") != "production" else None)
app.add_middleware(CORSMiddleware,
                   allow_origins=[os.environ.get("BACKEND_URL", "http://localhost:8000")],
                   allow_methods=["GET", "POST"], allow_headers=["*"])

def require_mt5():
    if not _mt5_connected:
        raise HTTPException(status_code=503, detail="MT5 mutasal nist")

@app.get("/ping")
async def ping():
    return {"status": "ok", "mt5_connected": _mt5_connected, "mt5_available": MT5_AVAILABLE,
            "uptime_seconds": round(time.time() - _start_time),
            "orders_executed": _order_count,
            "auth_required": bool(_GATEWAY_KEY),
            "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/account")
async def get_account(_: None = Depends(require_mt5), __: None = Depends(_verify_key)):
    info = mt5.account_info()
    if info is None: raise HTTPException(502, f"{mt5.last_error()}")
    return {"login": info.login, "server": info.server, "balance": info.balance,
            "equity": info.equity, "margin": info.margin, "free_margin": info.margin_free,
            "profit": info.profit, "currency": info.currency, "leverage": info.leverage, "name": info.name}

@app.post("/candles")
async def get_candles(req: CandleRequest, _: None = Depends(require_mt5), __: None = Depends(_verify_key)):
    rates = mt5.copy_rates_from_pos(req.symbol, _tf_const(req.timeframe), 0, req.count)
    if rates is None or len(rates) == 0: raise HTTPException(502, f"{mt5.last_error()}")
    return {"symbol": req.symbol, "timeframe": req.timeframe, "count": len(rates),
            "candles": [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]),
                         "low": float(r["low"]), "close": float(r["close"]), "volume": int(r["tick_volume"])}
                        for r in rates]}

@app.post("/order/open")
async def open_order(req: OrderRequest, _: None = Depends(require_mt5), __: None = Depends(_verify_key)):
    global _order_count
    info = mt5.symbol_info(req.symbol)
    if info is None: raise HTTPException(404, f"namad {req.symbol} pida nashad")
    pt   = info.point
    tick = mt5.symbol_info_tick(req.symbol)
    if tick is None: raise HTTPException(502, "khata dar daryaft gheyamt")
    if req.direction == "buy":
        ot = mt5.ORDER_TYPE_BUY;  price = tick.ask
        sl = price - req.sl_pips * pt * 10; tp = price + req.tp_pips * pt * 10
    else:
        ot = mt5.ORDER_TYPE_SELL; price = tick.bid
        sl = price + req.sl_pips * pt * 10; tp = price - req.tp_pips * pt * 10
    request = {"action": mt5.TRADE_ACTION_DEAL, "symbol": req.symbol, "volume": req.lot,
               "type": ot, "price": price, "sl": round(sl, info.digits), "tp": round(tp, info.digits),
               "deviation": req.deviation, "magic": req.magic,
               "comment": f"GV_{req.signal_id}" if req.signal_id else "GalaxyVast",
               "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
    result = mt5.order_send(request)
    # O-FIX-1: TRADE_RETCODE_DONE (E اضافه برداشته شد)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(502, f"retcode={result.retcode if result else -1}")
    _order_count += 1
    return {"ticket": result.order, "direction": req.direction, "lot": req.lot, "price": result.price, "retcode": result.retcode}

@app.post("/order/close")
async def close_order(req: CloseRequest, _: None = Depends(require_mt5), __: None = Depends(_verify_key)):
    pos = mt5.positions_get(ticket=req.ticket)
    if not pos: raise HTTPException(404, f"pozishion {req.ticket} pida nashad")
    p    = pos[0]; tick = mt5.symbol_info_tick(p.symbol)
    ot   = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
    price = tick.bid if p.type == 0 else tick.ask
    request = {"action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": req.lot or p.volume,
               "type": ot, "price": price, "position": req.ticket, "deviation": 20,
               "magic": p.magic, "comment": "GV_close", "type_time": mt5.ORDER_TIME_GTC,
               "type_filling": mt5.ORDER_FILLING_IOC}
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(502, f"retcode={result.retcode if result else -1}")
    return {"ticket": req.ticket, "closed": True}

@app.post("/order/modify")
async def modify_order(req: ModifyRequest, _: None = Depends(require_mt5), __: None = Depends(_verify_key)):
    pos = mt5.positions_get(ticket=req.ticket)
    if not pos: raise HTTPException(404, f"pozishion {req.ticket} pida nashad")
    p = pos[0]
    request = {"action": mt5.TRADE_ACTION_SLTP, "position": req.ticket, "symbol": p.symbol,
               "sl": req.sl if req.sl is not None else p.sl,
               "tp": req.tp if req.tp is not None else p.tp}
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(502, f"retcode={result.retcode if result else -1}")
    return {"ticket": req.ticket, "modified": True}

@app.get("/positions")
async def get_positions(_: None = Depends(require_mt5), __: None = Depends(_verify_key)):
    positions = mt5.positions_get() or []
    return {"count": len(positions), "positions": [
        {"ticket": p.ticket, "symbol": p.symbol, "type": "buy" if p.type == 0 else "sell",
         "volume": p.volume, "open_price": p.price_open, "sl": p.sl, "tp": p.tp, "profit": p.profit}
        for p in positions]}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--login",    type=int, default=0)
    parser.add_argument("--password", type=str, default="")
    parser.add_argument("--server",   type=str, default="")
    parser.add_argument("--host",     type=str, default="0.0.0.0")
    parser.add_argument("--port",     type=int, default=8080)
    args = parser.parse_args()
    if args.login:    os.environ["MT5_LOGIN"]    = str(args.login)
    if args.password: os.environ["MT5_PASSWORD"] = args.password
    if args.server:   os.environ["MT5_SERVER"]   = args.server
    uvicorn.run("agent:app", host=args.host, port=args.port, reload=False)
