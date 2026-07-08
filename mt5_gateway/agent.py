"""
mt5_gateway/agent.py
Galaxy Vast AI — MT5 Gateway Agent

فاز ۱ — هماهنگ‌سازی endpoint‌ها با MT5Connector

تغییرات:
  PHASE1-G1: GET /ping اضافه شد
  PHASE1-G2: GET /account/info alias برای /account
  PHASE1-G3: GET /symbol endpoint اطلاعات نماد
  PHASE1-G4: POST /candles حفظ شد
  PHASE1-G5: POST /order/open + alias /order/place
  PHASE1-G6: POST /order/close
  PHASE1-G7: POST /order/modify
  PHASE1-G8: GET /margin/calc اضافه شد
  PHASE1-G9: GET /history اضافه شد
  PHASE1-G10: auth header X-Gateway-Key
  PHASE1-G11: ORDER_FILLING پویا بر اساس symbol flags
  PHASE1-G12: SL/TP محاسبه بر اساس digits واقعی
"""
import os
import time
import argparse
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Security, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

_mt5_connected = False
_start_time    = time.time()
_order_count   = 0

_API_KEY_HEADER = APIKeyHeader(name="X-Gateway-Key", auto_error=False)
_GATEWAY_KEY    = os.environ.get("GATEWAY_API_KEY", "")


def _verify_key(_key: Optional[str] = Security(_API_KEY_HEADER)):
    if not _GATEWAY_KEY:
        return
    if _key != _GATEWAY_KEY:
        raise HTTPException(status_code=401, detail="X-Gateway-Key نامعتبر است")


class OrderRequest(BaseModel):
    symbol:    str
    direction: str
    lot:       float          = Field(gt=0)
    sl:        Optional[float] = None
    tp:        Optional[float] = None
    sl_pips:   float          = Field(default=50.0, ge=0)
    tp_pips:   float          = Field(default=100.0, ge=0)
    deviation: int            = Field(default=20, ge=0)
    magic:     int            = Field(default=202400)
    signal_id: Optional[str] = None
    comment:   str            = ""
    demo:      bool           = False


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
    count:     int = Field(default=100, ge=1, le=5000)


def _tf_const(tf: str) -> int:
    if not MT5_AVAILABLE:
        return 0
    mapping = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }
    return mapping.get(tf.upper(), mt5.TIMEFRAME_H1)


def _get_filling_mode(symbol: str) -> int:
    """PHASE1-G11: تعیین پویای ORDER_FILLING بر اساس flags نماد."""
    if not MT5_AVAILABLE:
        return 0
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    flags = info.filling_mode
    if flags & mt5.SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if flags & mt5.SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def _calc_sl_tp(direction, price, sl_pips, tp_pips, point, digits):
    """PHASE1-G12: محاسبه SL/TP بر اساس point واقعی نماد."""
    pip_size = point * 10
    sl_d = sl_pips * pip_size
    tp_d = tp_pips * pip_size
    if direction in ("buy", "BUY"):
        return round(price - sl_d, digits), round(price + tp_d, digits)
    return round(price + sl_d, digits), round(price - tp_d, digits)


def _require_mt5():
    if not _mt5_connected:
        raise HTTPException(status_code=503, detail="MT5 متصل نیست")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mt5_connected
    if MT5_AVAILABLE:
        login    = int(os.environ.get("MT5_LOGIN", "0") or "0")
        password = os.environ.get("MT5_PASSWORD", "")
        server   = os.environ.get("MT5_SERVER", "")
        if login and password and server:
            if mt5.initialize(login=login, password=password, server=server):
                _mt5_connected = True
                logger.info("[Gateway] MT5 متصل شد — login=%d", login)
            else:
                logger.error("[Gateway] MT5 اتصال ناموفق: %s", mt5.last_error())
        else:
            logger.warning("[Gateway] متغیرهای MT5 تنظیم نشده")
    else:
        logger.warning("[Gateway] MetaTrader5 موجود نیست")
    yield
    if _mt5_connected and MT5_AVAILABLE:
        mt5.shutdown()


app = FastAPI(
    title="Galaxy Vast MT5 Gateway",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("GATEWAY_ENV") != "production" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("BACKEND_URL", "http://localhost:8000")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/ping")
async def ping():
    """PHASE1-G1: health check — MT5Connector.connect() این را صدا می‌زند."""
    return {
        "status": "ok",
        "mt5_connected": _mt5_connected,
        "mt5_available": MT5_AVAILABLE,
        "uptime_seconds": round(time.time() - _start_time),
        "orders_executed": _order_count,
        "auth_required": bool(_GATEWAY_KEY),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/account")
async def get_account(
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    info = mt5.account_info()
    if info is None:
        raise HTTPException(502, f"خطای MT5: {mt5.last_error()}")
    return {
        "login": info.login, "server": info.server,
        "balance": info.balance, "equity": info.equity,
        "margin": info.margin, "free_margin": info.margin_free,
        "profit": info.profit, "currency": info.currency,
        "leverage": info.leverage, "name": info.name,
    }


@app.get("/account/info")
async def get_account_info(
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    """PHASE1-G2: alias برای /account."""
    return await get_account()


@app.get("/symbol")
async def get_symbol_info(
    symbol: str = Query(...),
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    """PHASE1-G3: اطلاعات نماد."""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise HTTPException(404, f"نماد '{symbol}' پیدا نشد")
    tick = mt5.symbol_info_tick(symbol)
    return {
        "symbol": symbol,
        "bid": tick.bid if tick else 0.0,
        "ask": tick.ask if tick else 0.0,
        "spread": info.spread, "digits": info.digits,
        "point": info.point,
        "trade_contract_size": info.trade_contract_size,
        "volume_min": info.volume_min, "volume_max": info.volume_max,
        "volume_step": info.volume_step, "filling_mode": info.filling_mode,
    }


@app.get("/symbol/info")
async def get_symbol_info_alias(
    symbol: str = Query(...),
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    return await get_symbol_info(symbol)


@app.post("/candles")
async def get_candles(
    req: CandleRequest,
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    rates = mt5.copy_rates_from_pos(req.symbol, _tf_const(req.timeframe), 0, req.count)
    if rates is None or len(rates) == 0:
        raise HTTPException(502, f"خطای MT5: {mt5.last_error()}")
    return {
        "symbol": req.symbol, "timeframe": req.timeframe, "count": len(rates),
        "candles": [
            {"time": int(r["time"]), "open": float(r["open"]),
             "high": float(r["high"]), "low": float(r["low"]),
             "close": float(r["close"]), "volume": int(r["tick_volume"])}
            for r in rates
        ],
    }


@app.post("/order/open")
async def open_order(
    req: OrderRequest,
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    global _order_count
    info = mt5.symbol_info(req.symbol)
    if info is None:
        raise HTTPException(404, f"نماد '{req.symbol}' پیدا نشد")
    tick = mt5.symbol_info_tick(req.symbol)
    if tick is None:
        raise HTTPException(502, "خطا در دریافت قیمت")

    direction = req.direction.lower()
    if direction == "buy":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    elif direction == "sell":
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        raise HTTPException(400, f"direction نامعتبر: {req.direction}")

    if req.sl is not None and req.tp is not None:
        sl = round(req.sl, info.digits)
        tp = round(req.tp, info.digits)
    else:
        sl, tp = _calc_sl_tp(direction, price, req.sl_pips, req.tp_pips,
                              info.point, info.digits)

    filling = _get_filling_mode(req.symbol)
    comment = req.comment or (f"GV_{req.signal_id}" if req.signal_id else "GalaxyVast")

    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": req.symbol,
        "volume": req.lot, "type": order_type, "price": price,
        "sl": sl, "tp": tp, "deviation": req.deviation, "magic": req.magic,
        "comment": comment, "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(502, f"retcode={result.retcode if result else -1}")
    _order_count += 1
    return {"ticket": result.order, "direction": direction, "lot": req.lot,
            "price": result.price, "sl": sl, "tp": tp, "retcode": result.retcode}


@app.post("/order/place")
async def place_order_alias(
    req: OrderRequest,
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    return await open_order(req)


@app.post("/order/close")
async def close_order(
    req: CloseRequest,
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    positions = mt5.positions_get(ticket=req.ticket)
    if not positions:
        raise HTTPException(404, f"پوزیشن {req.ticket} پیدا نشد")
    p = positions[0]
    tick = mt5.symbol_info_tick(p.symbol)
    filling = _get_filling_mode(p.symbol)
    order_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
    price = tick.bid if p.type == 0 else tick.ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol,
        "volume": req.lot or p.volume, "type": order_type, "price": price,
        "position": req.ticket, "deviation": 20, "magic": p.magic,
        "comment": "GV_close", "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(502, f"retcode={result.retcode if result else -1}")
    return {"ticket": req.ticket, "closed": True, "retcode": result.retcode}


@app.post("/order/modify")
async def modify_order(
    req: ModifyRequest,
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    positions = mt5.positions_get(ticket=req.ticket)
    if not positions:
        raise HTTPException(404, f"پوزیشن {req.ticket} پیدا نشد")
    p = positions[0]
    request = {
        "action": mt5.TRADE_ACTION_SLTP, "position": req.ticket,
        "symbol": p.symbol,
        "sl": req.sl if req.sl is not None else p.sl,
        "tp": req.tp if req.tp is not None else p.tp,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(502, f"retcode={result.retcode if result else -1}")
    return {"ticket": req.ticket, "modified": True}


@app.get("/positions")
async def get_positions(
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    positions = mt5.positions_get() or []
    return {
        "count": len(positions),
        "positions": [
            {"ticket": p.ticket, "symbol": p.symbol,
             "type": "buy" if p.type == 0 else "sell",
             "direction": "BUY" if p.type == 0 else "SELL",
             "volume": p.volume, "open_price": p.price_open,
             "sl": p.sl, "tp": p.tp, "profit": p.profit, "comment": p.comment}
            for p in positions
        ],
    }


@app.get("/margin/calc")
async def calc_margin(
    symbol: str   = Query(...),
    volume: float = Query(...),
    type:   str   = Query(default="BUY"),
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    """PHASE1-G8: محاسبه margin مورد نیاز."""
    order_type = mt5.ORDER_TYPE_BUY if type.upper() == "BUY" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise HTTPException(502, f"نماد '{symbol}' قیمتی ندارد")
    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    margin = mt5.order_calc_margin(order_type, symbol, volume, price)
    if margin is None:
        raise HTTPException(502, f"محاسبه margin ناموفق: {mt5.last_error()}")
    return {"symbol": symbol, "volume": volume, "type": type.upper(),
            "margin": round(margin, 2), "price": price}


@app.get("/history")
async def get_history(
    from_ts: int = Query(..., alias="from"),
    to_ts:   int = Query(..., alias="to"),
    _: None = Depends(_require_mt5),
    __: None = Depends(_verify_key),
):
    """PHASE1-G9: تاریخچه معاملات."""
    from datetime import datetime as dt
    deals = mt5.history_deals_get(dt.fromtimestamp(from_ts), dt.fromtimestamp(to_ts)) or []
    return {
        "count": len(deals),
        "deals": [
            {"ticket": d.ticket, "order": d.order, "symbol": d.symbol,
             "type": "buy" if d.type == 0 else "sell",
             "volume": d.volume, "price": d.price, "profit": d.profit,
             "commission": d.commission, "swap": d.swap,
             "time": int(d.time), "comment": d.comment}
            for d in deals
        ],
    }


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
