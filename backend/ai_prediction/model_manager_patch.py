"""
backend/ai_prediction/model_manager_patch.py — Phase S patch
S-2a: asyncio.Lock on _cache mutations
S-2b: get() returns None on miss — never raises
S-2c: warm_up() async startup preload
S-2d: LRU eviction under lock

Backward compatible.
"""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_prediction.model_manager")

MAX_CACHED_MODELS = 10
_WARM_UP_SYMBOLS  = ["XAUUSD", "EURUSD", "GBPUSD"]


@dataclass
class _CacheEntry:
    model:      Any
    version:    str
    loaded_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    hit_count:  int = 0


class SafeModelCache:
    """
    Async-safe LRU model cache.
    S-2a: asyncio.Lock on all mutations
    S-2b: get() returns None on miss
    S-2c: warm_up() preload
    S-2d: LRU eviction under lock
    """

    def __init__(self, maxsize: int = MAX_CACHED_MODELS) -> None:
        self._maxsize = maxsize
        self._cache:  OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock:   asyncio.Lock = asyncio.Lock()

    async def get(self, symbol: str) -> Optional[Any]:
        """S-2b: return None on miss."""
        async with self._lock:
            entry = self._cache.get(symbol)
            if entry is None:
                return None
            entry.hit_count += 1
            self._cache.move_to_end(symbol)
            return entry.model

    async def put(self, symbol: str, model: Any, version: str = "unknown") -> None:
        """S-2a + S-2d: insert under lock, evict LRU if over capacity."""
        async with self._lock:
            if symbol in self._cache:
                del self._cache[symbol]
            while len(self._cache) >= self._maxsize:
                evicted, _ = self._cache.popitem(last=False)
                logger.debug("ModelCache: evicted %s (LRU)", evicted)
            self._cache[symbol] = _CacheEntry(model=model, version=version)
            self._cache.move_to_end(symbol)

    async def invalidate(self, symbol: str) -> bool:
        async with self._lock:
            if symbol in self._cache:
                del self._cache[symbol]
                return True
            return False

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def stats(self) -> Dict[str, Any]:
        async with self._lock:
            return {
                "cached_symbols": len(self._cache),
                "max_size":       self._maxsize,
                "symbols": [
                    {"symbol": k, "version": v.version, "hits": v.hit_count,
                     "age_s": (datetime.now(timezone.utc) - v.loaded_at).total_seconds()}
                    for k, v in self._cache.items()
                ],
            }

    async def warm_up(self, loader_fn, symbols: Optional[List[str]] = None) -> None:
        """S-2c: startup preload."""
        targets = symbols or _WARM_UP_SYMBOLS
        for sym in targets:
            try:
                result = await loader_fn(sym)
                if result is not None:
                    model, version = result
                    await self.put(sym, model, version)
            except Exception as exc:
                logger.warning("ModelCache: warm-up failed %s: %s", sym, exc)


def patch_model_manager_class(cls: type) -> type:
    """Inject SafeModelCache into an existing ModelManager class."""
    import asyncio as _asyncio

    original_init = cls.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if not isinstance(getattr(self, "_safe_cache", None), SafeModelCache):
            self._safe_cache = SafeModelCache(maxsize=MAX_CACHED_MODELS)
        if not hasattr(self, "_lock"):
            self._lock = _asyncio.Lock()

    cls.__init__ = patched_init

    async def load_safe(self, symbol: str, force_reload: bool = False) -> Optional[Any]:
        if not force_reload:
            cached = await self._safe_cache.get(symbol)
            if cached is not None:
                return cached
        try:
            async with self._lock:
                if not force_reload:
                    cached = await self._safe_cache.get(symbol)
                    if cached is not None:
                        return cached
                model, version = await _asyncio.to_thread(self._load_from_disk, symbol)
                await self._safe_cache.put(symbol, model, version)
                return model
        except FileNotFoundError:
            logger.debug("ModelManager: no model on disk for %s", symbol)
            return None
        except Exception as exc:
            logger.warning("ModelManager: load failed %s: %s", symbol, exc)
            return None

    cls.load = load_safe

    async def warm_up_manager(self, symbols=None):
        async def _loader(sym):
            try:
                return await _asyncio.to_thread(self._load_from_disk, sym)
            except Exception:
                return None
        await self._safe_cache.warm_up(_loader, symbols)

    cls.warm_up = warm_up_manager
    logger.debug("ModelManager class patched (S-2): %s", cls.__name__)
    return cls
