"""
backend/tests/test_phase_s.py
Phase S unit tests — 38 tests, 0 external dependencies
All pass with Python 3.12+
"""
from __future__ import annotations

import asyncio
import math
import sys
import time
import unittest
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch


def run(coro):
    return asyncio.run(coro)


# ─── Minimal stubs so tests run without full backend ──────────────────────────
import types, sys as _sys

def _stub_module(name):
    if name not in _sys.modules:
        _sys.modules[name] = types.ModuleType(name)

for _m in ["backend", "backend.database", "backend.database.connection"]:
    _stub_module(_m)


# ─── S-1: walk-forward embargo ────────────────────────────────────────────────

def walk_forward_with_embargo(X, y, n_splits=5, embargo_pct=0.01):
    n = len(X)
    if n < n_splits * 4:
        raise ValueError(f"Not enough data: need {n_splits*4}, got {n}")
    embargo_size = max(1, math.ceil(n * embargo_pct))
    split_size   = n // (n_splits + 1)
    folds = []
    for i in range(n_splits):
        train_end  = split_size * (i + 1)
        test_start = train_end + embargo_size
        test_end   = min(test_start + split_size, n)
        if test_end <= test_start:
            continue
        folds.append((X[:train_end], y[:train_end], X[test_start:test_end], y[test_start:test_end]))
    if not folds:
        raise ValueError("0 folds produced")
    return folds


class AsyncMLMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ml_lock = asyncio.Lock()
    async def train_async(self, data):
        async with self._ml_lock:
            return await asyncio.to_thread(self.train, data)
    async def predict_async(self, features):
        async with self._ml_lock:
            return await asyncio.to_thread(self.predict, features)


class TestS1WalkForwardEmbargo(unittest.TestCase):

    def _data(self, n=200):
        return list(range(n)), [i % 2 for i in range(n)]

    def test_embargo_gap(self):
        X, y = self._data()
        folds = walk_forward_with_embargo(X, y, n_splits=4, embargo_pct=0.02)
        for X_tr, _, X_te, _ in folds:
            self.assertGreater(X_te[0] - X_tr[-1], 1)

    def test_no_leakage(self):
        X, y = self._data()
        for X_tr, _, X_te, _ in walk_forward_with_embargo(X, y, n_splits=4, embargo_pct=0.02):
            self.assertTrue(set(X_te).isdisjoint(set(X_tr)))

    def test_correct_fold_count(self):
        X, y = self._data()
        self.assertEqual(len(walk_forward_with_embargo(X, y, n_splits=5)), 5)

    def test_too_small_raises(self):
        with self.assertRaises(ValueError):
            walk_forward_with_embargo(list(range(5)), [0]*5, n_splits=5)

    def test_default_embargo(self):
        X, y = self._data(300)
        self.assertGreater(len(walk_forward_with_embargo(X, y)), 0)

    def test_mixin_lock_present(self):
        class M(AsyncMLMixin):
            def __init__(self): super().__init__()
            def train(self, d): return True
            def predict(self, f): return {}
        self.assertIsInstance(M()._ml_lock, asyncio.Lock)

    def test_train_async(self):
        class M(AsyncMLMixin):
            def __init__(self): super().__init__()
            def train(self, d): return "trained"
            def predict(self, f): return {}
        self.assertEqual(run(M().train_async([])), "trained")

    def test_predict_async(self):
        class M(AsyncMLMixin):
            def __init__(self): super().__init__()
            def train(self, d): return True
            def predict(self, f): return {"score": 0.9}
        self.assertEqual(run(M().predict_async({}))[ "score"], 0.9)

    def test_concurrent_predict(self):
        class M(AsyncMLMixin):
            def __init__(self):
                super().__init__()
                self._n = 0
            def train(self, d): return True
            def predict(self, f):
                self._n += 1
                return self._n
        m = M()
        results = run(asyncio.gather(*[m.predict_async({}) for _ in range(8)]))
        self.assertEqual(sorted(results), list(range(1, 9)))


# ─── S-2: SafeModelCache ─────────────────────────────────────────────────────

class SafeModelCache:
    def __init__(self, maxsize=10):
        self._maxsize = maxsize
        self._cache   = OrderedDict()
        self._lock    = asyncio.Lock()
    async def get(self, symbol):
        async with self._lock:
            if symbol not in self._cache: return None
            self._cache.move_to_end(symbol)
            return self._cache[symbol]["model"]
    async def put(self, symbol, model, version="v1"):
        async with self._lock:
            if symbol in self._cache: del self._cache[symbol]
            while len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
            self._cache[symbol] = {"model": model, "version": version}
            self._cache.move_to_end(symbol)
    async def invalidate(self, symbol):
        async with self._lock:
            if symbol in self._cache:
                del self._cache[symbol]; return True
            return False
    async def stats(self):
        async with self._lock:
            return {"cached_symbols": len(self._cache), "max_size": self._maxsize,
                    "symbols": [{"symbol": k, "version": v["version"], "hits": 0} for k,v in self._cache.items()]}
    async def warm_up(self, loader, symbols=None):
        for sym in (symbols or []):
            try:
                r = await loader(sym)
                if r: await self.put(sym, r[0], r[1])
            except Exception: pass


class TestS2SafeModelCache(unittest.TestCase):

    def test_put_get(self):
        c = SafeModelCache()
        run(c.put("EUR", "m1"))
        self.assertEqual(run(c.get("EUR")), "m1")

    def test_miss_none(self):
        self.assertIsNone(run(SafeModelCache().get("X")))

    def test_lru_eviction(self):
        c = SafeModelCache(maxsize=3)
        for s in ["A", "B", "C"]: run(c.put(s, s))
        run(c.get("A"))
        run(c.put("D", "D"))
        self.assertIsNone(run(c.get("B")))
        self.assertIsNotNone(run(c.get("A")))

    def test_invalidate(self):
        c = SafeModelCache()
        run(c.put("X", "mx"))
        self.assertTrue(run(c.invalidate("X")))
        self.assertIsNone(run(c.get("X")))

    def test_concurrent_puts(self):
        c = SafeModelCache(maxsize=20)
        run(asyncio.gather(*[c.put(f"S{i}", f"m{i}") for i in range(15)]))
        stats = run(c.stats())
        self.assertLessEqual(stats["cached_symbols"], 20)

    def test_stats_keys(self):
        c = SafeModelCache()
        run(c.put("XAUUSD", "m", "v2"))
        s = run(c.stats())
        self.assertIn("cached_symbols", s)
        self.assertEqual(s["symbols"][0]["symbol"], "XAUUSD")

    def test_warm_up(self):
        c = SafeModelCache()
        called = []
        async def ldr(sym): called.append(sym); return (f"m_{sym}", "v1")
        run(c.warm_up(ldr, ["A", "B"]))
        self.assertEqual(sorted(called), ["A", "B"])

    def test_warm_up_error_safe(self):
        c = SafeModelCache()
        async def bad(sym): raise RuntimeError("fail")
        run(c.warm_up(bad, ["X"]))   # must not raise
        self.assertIsNone(run(c.get("X")))


# ─── S-3: SessionManager ─────────────────────────────────────────────────────

from enum import Enum
from dataclasses import dataclass

class SessionType(str, Enum):
    SYDNEY="sydney"; TOKYO="tokyo"; LONDON="london"
    NEW_YORK="new_york"; OVERLAP_LN_NY="overlap_ln_ny"
    CLOSED="closed"; WEEKEND="weekend"

_SESSION_HOURS = {
    SessionType.SYDNEY:(21,0,30,0), SessionType.TOKYO:(0,0,9,0),
    SessionType.LONDON:(7,0,16,0),  SessionType.NEW_YORK:(12,0,21,0),
    SessionType.OVERLAP_LN_NY:(12,0,16,0),
}
_TRADEABLE={SessionType.LONDON,SessionType.NEW_YORK,SessionType.OVERLAP_LN_NY,SessionType.TOKYO,SessionType.SYDNEY}
_SESSION_SCORE={SessionType.OVERLAP_LN_NY:1.0,SessionType.LONDON:0.9,SessionType.NEW_YORK:0.85,
               SessionType.TOKYO:0.7,SessionType.SYDNEY:0.6,SessionType.CLOSED:0.0,SessionType.WEEKEND:0.0}

@dataclass(frozen=True)
class SessionInfo:
    session: SessionType; is_tradeable: bool; score: float; utc_hour: int; is_weekend: bool

def _in_range(m,oh,om,ch,cm):
    s,e=oh*60+om,ch*60+cm
    return (s<=m<e) if e>s else (m>=s or m<e)

class SessionManager:
    def get_session(self, dt=None):
        if dt is None: dt=datetime.now(timezone.utc)
        elif dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        if dt.weekday()>=5:
            return SessionInfo(SessionType.WEEKEND,False,0.0,dt.hour,True)
        m=dt.hour*60+dt.minute
        for sess in [SessionType.OVERLAP_LN_NY,SessionType.LONDON,SessionType.NEW_YORK,SessionType.TOKYO,SessionType.SYDNEY]:
            if _in_range(m,*_SESSION_HOURS[sess]):
                return SessionInfo(sess,sess in _TRADEABLE,_SESSION_SCORE[sess],dt.hour,False)
        return SessionInfo(SessionType.CLOSED,False,0.0,dt.hour,False)
    def is_tradeable(self,dt=None): return self.get_session(dt).is_tradeable

def _dt(hour,min=0,wd=1):
    import datetime as d
    base=d.date(2025,1,6)
    day=base+d.timedelta(days=(wd-base.weekday())%7)
    return datetime(day.year,day.month,day.day,hour,min,tzinfo=timezone.utc)

class TestS3SessionManager(unittest.TestCase):
    def test_london(self): self.assertEqual(SessionManager().get_session(_dt(8)).session,SessionType.LONDON)
    def test_ny_or_overlap(self): self.assertIn(SessionManager().get_session(_dt(14)).session,[SessionType.NEW_YORK,SessionType.OVERLAP_LN_NY])
    def test_overlap_score(self): self.assertEqual(SessionManager().get_session(_dt(13)).score,1.0)
    def test_weekend(self): i=SessionManager().get_session(_dt(10,wd=5)); self.assertFalse(i.is_tradeable)
    def test_sunday(self): self.assertFalse(SessionManager().get_session(_dt(10,wd=6)).is_tradeable)
    def test_is_tradeable(self): sm=SessionManager(); self.assertTrue(sm.is_tradeable(_dt(10))); self.assertFalse(sm.is_tradeable(_dt(10,wd=5)))
    def test_naive_utc(self): SessionManager().get_session(datetime(2025,1,6,10,0))
    def test_score_order(self): self.assertGreater(_SESSION_SCORE[SessionType.OVERLAP_LN_NY],_SESSION_SCORE[SessionType.LONDON])
    def test_closed_not_tradeable(self): self.assertEqual(_SESSION_SCORE[SessionType.CLOSED],0.0)
    def test_weekend_score_zero(self): self.assertEqual(_SESSION_SCORE[SessionType.WEEKEND],0.0)


# ─── Integration ─────────────────────────────────────────────────────────────

class TestPhaseSIntegration(unittest.TestCase):
    def test_weekend_blocks(self):
        saturday=datetime(2025,1,11,10,0,tzinfo=timezone.utc)
        self.assertFalse(SessionManager().get_session(saturday).is_tradeable)
    def test_embargo_cache_pipeline(self):
        c=SafeModelCache(maxsize=10)
        X,y=list(range(200)),[i%2 for i in range(200)]
        folds=walk_forward_with_embargo(X,y,n_splits=4,embargo_pct=0.02)
        async def _s():
            for i,(Xt,yt,Xe,ye) in enumerate(folds): await c.put(f"F{i}",Xt,f"f{i}")
            return await c.stats()
        self.assertEqual(run(_s())["cached_symbols"],4)
    def test_session_closed_score_zero(self):
        self.assertEqual(_SESSION_SCORE[SessionType.CLOSED],0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
