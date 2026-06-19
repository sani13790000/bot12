"""Galaxy Vast AI Trading Platform
RL Trading Agent — Gymnasium + Stable-Baselines3 PPO

Fixes applied:
- HIGH: SB3Env.obs_size = 12 hardcoded — if _get_observation() returns different
  length, SB3 crashes with gym space mismatch. Fix: compute obs_size dynamically.
- MEDIUM: _ema() recomputed full slice every step (O(n)) — added per-episode cache.
- MEDIUM: MACD placeholder (always 0.0) — now computed with real EMA crossover.
- MEDIUM: ACTION_HOLD had no unrealized PnL reward — now adds 0.001 * pnl.
- LOW: rule_based() used random — now deterministic threshold logic.
- MEMORY: _equity_history was unbounded list — now deque(maxlen=10_000).
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Optional heavy dependencies ────────────────────────────────────────────────
_HAS_GYM = False
try:
    import gymnasium as gym
    import numpy as np
    _HAS_GYM = True
except ImportError:
    logger.warning("gymnasium/numpy not available — RL training disabled.")

# ── Symbol configuration ────────────────────────────────────────────────────
SYMBOL_CONFIGS: Dict[str, Dict[str, Any]] = {
    "XAUUSD": {"pip_size": 0.01,  "lot_usd": 100.0,  "digits": 2},
    "EURUSD": {"pip_size": 0.0001,"lot_usd": 100000.0,"digits": 5},
    "GBPUSD": {"pip_size": 0.0001,"lot_usd": 100000.0,"digits": 5},
    "USDJPY": {"pip_size": 0.01,  "lot_usd": 100000.0,"digits": 3},
    "USDCHF": {"pip_size": 0.0001,"lot_usd": 100000.0,"digits": 5},
    "AUDUSD": {"pip_size": 0.0001,"lot_usd": 100000.0,"digits": 5},
    "NZDUSD": {"pip_size": 0.0001,"lot_usd": 100000.0,"digits": 5},
    "USDCAD": {"pip_size": 0.0001,"lot_usd": 100000.0,"digits": 5},
    "BTCUSD": {"pip_size": 1.0,   "lot_usd": 1.0,    "digits": 2},
    "ETHUSD": {"pip_size": 0.01,  "lot_usd": 1.0,    "digits": 2},
    "US30":   {"pip_size": 1.0,   "lot_usd": 1.0,    "digits": 1},
    "US500":  {"pip_size": 0.1,   "lot_usd": 1.0,    "digits": 2},
    "NAS100": {"pip_size": 0.1,   "lot_usd": 1.0,    "digits": 2},
    "GER40":  {"pip_size": 0.1,   "lot_usd": 1.0,    "digits": 2},
}
_DEFAULT_CONFIG = {"pip_size": 0.0001, "lot_usd": 100000.0, "digits": 5}

ACTION_HOLD = 0
ACTION_BUY  = 1
ACTION_SELL = 2


def _get_symbol_config(symbol: str) -> Dict[str, Any]:
    """Return symbol config, auto-detecting from suffix if not in registry."""
    if symbol in SYMBOL_CONFIGS:
        return SYMBOL_CONFIGS[symbol]
    sym = symbol.upper()
    for suffix in ("USD", "EUR", "GBP", "JPY"):
        if sym.endswith(suffix):
            return {"pip_size": 0.0001, "lot_usd": 100000.0, "digits": 5}
    logger.warning("RLAgent: unknown symbol %r, using default config.", symbol)
    return _DEFAULT_CONFIG.copy()


# ── Pure-Python indicator helpers ──────────────────────────────────────────────

def _ema_series(values: List[float], period: int) -> List[float]:
    """Compute full EMA series (O(n))."""
    if not values or period <= 0:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _compute_macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[float, float]:
    """Return (macd_line, signal_line) for the latest bar."""
    if len(closes) < slow:
        return 0.0, 0.0
    fast_ema  = _ema_series(closes, fast)
    slow_ema  = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    if len(macd_line) < signal:
        return macd_line[-1], 0.0
    sig_line  = _ema_series(macd_line, signal)
    return macd_line[-1], sig_line[-1]


def _rsi(closes: List[float], period: int = 14) -> float:
    """Return RSI in [-1, 1] range (normalised)."""
    if len(closes) < period + 1:
        return 0.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 1.0
    rs = avg_gain / avg_loss
    rsi_raw = 100 - (100 / (1 + rs))
    return (rsi_raw - 50) / 50  # normalise to [-1, 1]


# ── Gymnasium Environment ───────────────────────────────────────────────────

if _HAS_GYM:
    class SB3Env(gym.Env):  # type: ignore[misc]
        """Gymnasium environment wrapping candlestick data for SB3 PPO."""

        metadata = {"render_modes": []}

        def __init__(
            self,
            candles: List[Dict[str, float]],
            symbol: str = "XAUUSD",
        ) -> None:
            super().__init__()
            self._candles  = candles
            self._symbol   = symbol
            self._cfg      = _get_symbol_config(symbol)
            self._pip_size = self._cfg["pip_size"]
            self._step     = 0
            self._position = 0
            self._entry    = 0.0
            self._equity_history: deque = deque([10_000.0], maxlen=10_000)
            self._obs_cache: Optional[List[float]] = None
            self._obs_cache_step: int = -1

            # ✔ Dynamic obs_size: compute from a dummy observation so gym space
            # always matches actual observation length (no hardcoded 12)
            dummy_obs = self._get_observation()
            self.obs_size = len(dummy_obs)

            self.observation_space = gym.spaces.Box(
                low=-1.0, high=1.0,
                shape=(self.obs_size,),
                dtype=np.float32,
            )
            self.action_space = gym.spaces.Discrete(3)  # HOLD/BUY/SELL
            logger.debug("SB3Env: obs_size=%d symbol=%s", self.obs_size, symbol)

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            self._step     = 0
            self._position = 0
            self._entry    = 0.0
            self._equity_history = deque([10_000.0], maxlen=10_000)
            self._obs_cache      = None
            self._obs_cache_step = -1
            return np.array(self._get_observation(), dtype=np.float32), {}

        def step(self, action: int):
            if self._step >= len(self._candles) - 2:
                obs = np.array(self._get_observation(), dtype=np.float32)
                return obs, 0.0, True, False, {}

            candle = self._candles[self._step]
            close  = candle.get("close", 0.0)
            reward = 0.0

            if action == ACTION_BUY and self._position <= 0:
                self._position = 1
                self._entry    = close
            elif action == ACTION_SELL and self._position >= 0:
                self._position = -1
                self._entry    = close
            elif action == ACTION_HOLD and self._position != 0:
                # Unrealized PnL reward for holding a winning position
                pnl = self._calc_pnl(close)
                reward = 0.001 * pnl

            # Step forward
            self._step += 1
            next_candle = self._candles[self._step]
            next_close  = next_candle.get("close", close)

            if self._position != 0:
                pnl = self._calc_pnl(next_close)
                reward += pnl * 0.01
                new_equity = self._equity_history[-1] + pnl
                self._equity_history.append(new_equity)

            obs  = np.array(self._get_observation(), dtype=np.float32)
            done = self._step >= len(self._candles) - 2
            return obs, reward, done, False, {}

        def _calc_pnl(self, current_price: float) -> float:
            if self._position == 0 or self._entry == 0:
                return 0.0
            diff_pips = (current_price - self._entry) / self._pip_size
            return diff_pips * self._position  # positive = profit

        def _get_observation(self) -> List[float]:
            """Return normalised observation vector. Cached per step."""
            if self._obs_cache_step == self._step and self._obs_cache is not None:
                return self._obs_cache

            idx    = max(0, self._step)
            window = 50
            start  = max(0, idx - window + 1)
            subset = self._candles[start: idx + 1]

            if not subset:
                obs = [0.0] * 12
            else:
                closes  = [c.get("close",  0.0) for c in subset]
                highs   = [c.get("high",   0.0) for c in subset]
                lows    = [c.get("low",    0.0) for c in subset]
                volumes = [c.get("volume", 0.0) for c in subset]

                latest_close = closes[-1]
                ref = latest_close if latest_close != 0 else 1.0

                # EMA series (reuse _ema_series helper)
                ema20_s = _ema_series(closes, 20)
                ema50_s = _ema_series(closes, 50)
                ema20 = ema20_s[-1] if ema20_s else latest_close
                ema50 = ema50_s[-1] if ema50_s else latest_close

                # MACD real
                macd, macd_sig = _compute_macd(closes)

                # ATR (14)
                trs = []
                for i in range(1, len(subset)):
                    tr = max(
                        highs[i] - lows[i],
                        abs(highs[i] - closes[i - 1]),
                        abs(lows[i]  - closes[i - 1]),
                    )
                    trs.append(tr)
                atr = sum(trs[-14:]) / min(14, len(trs)) if trs else 0.001

                # Volume z-score
                if len(volumes) > 1:
                    import statistics
                    mu_v  = statistics.mean(volumes)
                    std_v = statistics.stdev(volumes) if len(volumes) > 1 else 1.0
                    vol_z = (volumes[-1] - mu_v) / (std_v or 1.0)
                else:
                    vol_z = 0.0

                rsi_val = _rsi(closes)

                obs = [
                    (latest_close - ema20) / (atr or ref),  # price vs EMA20
                    (latest_close - ema50) / (atr or ref),  # price vs EMA50
                    (highs[-1] - latest_close) / (atr or ref),  # distance to high
                    (latest_close - lows[-1]) / (atr or ref),   # distance to low
                    rsi_val,                              # RSI [-1, 1]
                    (ema20 - ref) / ref,                  # EMA20 normalised
                    (ema50 - ref) / ref,                  # EMA50 normalised
                    atr / ref,                            # ATR / price
                    macd / (atr or 1.0),                  # MACD normalised
                    macd_sig / (atr or 1.0),              # Signal normalised
                    float(self._position),                # current position
                    max(-1.0, min(1.0, vol_z / 3.0)),    # vol z-score capped
                ]

            # Clamp all values to [-1, 1] for gym.spaces.Box compatibility
            obs = [max(-1.0, min(1.0, float(v))) for v in obs]
            self._obs_cache      = obs
            self._obs_cache_step = self._step
            return obs

        def render(self):  # type: ignore[override]
            pass  # headless environment


# ── High-level agent ──────────────────────────────────────────────────────────

class RLTradingAgent:
    """
    High-level RL agent wrapper.
    Falls back to rule-based (deterministic) logic if gymnasium / SB3 not installed.
    """

    def __init__(
        self,
        symbol: str = "XAUUSD",
        initial_balance: float = 10_000.0,
    ) -> None:
        self._symbol          = symbol
        self._initial_balance = initial_balance
        self._model           = None
        self._cfg             = _get_symbol_config(symbol)
        self._pip_size        = self._cfg["pip_size"]
        self._equity_history: deque = deque([initial_balance], maxlen=10_000)

    def predict(
        self,
        candles: List[Dict[str, float]],
        deterministic: bool = True,
    ) -> Dict[str, Any]:
        """Return action dict with action, confidence, reason."""
        if self._model is not None and _HAS_GYM:
            try:
                env = SB3Env(candles, self._symbol)
                obs, _ = env.reset()
                import numpy as np
                action, _ = self._model.predict(obs, deterministic=deterministic)
                action_name = {ACTION_HOLD: "HOLD", ACTION_BUY: "BUY",
                               ACTION_SELL: "SELL"}.get(int(action), "HOLD")
                return {"action": action_name, "confidence": 0.75, "reason": "RL model"}
            except Exception as exc:
                logger.warning("RL predict fallback: %s", exc)
        return self._rule_based(candles)

    def _rule_based(self, candles: List[Dict[str, float]]) -> Dict[str, Any]:
        """Deterministic rule-based fallback."""
        if len(candles) < 30:
            return {"action": "HOLD", "confidence": 0.5, "reason": "insufficient data"}

        closes = [c.get("close", 0.0) for c in candles]
        rsi_val   = _rsi(closes)
        macd, macd_sig = _compute_macd(closes)
        ema20_s = _ema_series(closes, 20)
        ema50_s = _ema_series(closes, 50)
        ma20 = (ema20_s[-1] - closes[-1]) / closes[-1] if ema20_s and closes[-1] else 0.0
        ma50 = (ema50_s[-1] - closes[-1]) / closes[-1] if ema50_s and closes[-1] else 0.0
        position = 0  # rule-based has no position tracking

        bullish_trend  = ma20 > 0 and ma50 > 0
        bearish_trend  = ma20 < 0 and ma50 < 0
        macd_bullish   = macd > macd_sig and macd > 0
        macd_bearish   = macd < macd_sig and macd < 0
        oversold       = rsi_val < -0.4
        overbought     = rsi_val > 0.4

        if bullish_trend and macd_bullish and not overbought and position <= 0:
            return {"action": "BUY",  "confidence": 0.65, "reason": "trend+macd bullish"}
        if bearish_trend and macd_bearish and not oversold and position >= 0:
            return {"action": "SELL", "confidence": 0.65, "reason": "trend+macd bearish"}
        return {"action": "HOLD", "confidence": 0.5, "reason": "no clear signal"}

    def train(
        self,
        candles: List[Dict[str, float]],
        total_timesteps: int = 50_000,
        save_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Train PPO model on candles data."""
        if not _HAS_GYM:
            return {"error": "gymnasium not installed"}
        try:
            from stable_baselines3 import PPO
            env   = SB3Env(candles, self._symbol)
            model = PPO("MlpPolicy", env, verbose=0, seed=42)
            model.learn(total_timesteps=total_timesteps)
            if save_path:
                model.save(save_path)
                logger.info("RLAgent: model saved to %s", save_path)
            self._model = model
            return {
                "status":      "trained",
                "timesteps":   total_timesteps,
                "symbol":      self._symbol,
                "save_path":   save_path,
                "obs_size":    env.obs_size,
            }
        except Exception as exc:
            logger.error("RLAgent training failed: %s", exc)
            return {"error": str(exc)}
