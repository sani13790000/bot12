"""Reinforcement Learning Trading Agent — Galaxy Vast Institutional.

Fixes applied:
- CRITICAL: MACD computed with real EMA calculation (not placeholder 0.0)
- MEDIUM: _get_observation() result cached per step to avoid O(n) per call
- MEDIUM: ACTION_HOLD now includes unrealized PnL in reward
- HIGH: _equity_history uses deque(maxlen=10_000) to prevent memory leak
- LOW: rule-based fallback is deterministic (no random)
"""
from __future__ import annotations

import logging
import math
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Symbol configuration (pip_size, lot_size, pip_value)
# ---------------------------------------------------------------------------
SYMBOL_CONFIGS: Dict[str, Dict[str, float]] = {
    "XAUUSD": {"pip_size": 0.1,    "lot_size": 100.0,    "pip_value": 1.0},
    "EURUSD": {"pip_size": 0.0001, "lot_size": 100_000.0, "pip_value": 10.0},
    "GBPUSD": {"pip_size": 0.0001, "lot_size": 100_000.0, "pip_value": 10.0},
    "USDJPY": {"pip_size": 0.01,   "lot_size": 100_000.0, "pip_value": 9.09},
    "USDCHF": {"pip_size": 0.0001, "lot_size": 100_000.0, "pip_value": 10.0},
    "AUDUSD": {"pip_size": 0.0001, "lot_size": 100_000.0, "pip_value": 10.0},
    "NZDUSD": {"pip_size": 0.0001, "lot_size": 100_000.0, "pip_value": 10.0},
    "USDCAD": {"pip_size": 0.0001, "lot_size": 100_000.0, "pip_value": 10.0},
    "EURGBP": {"pip_size": 0.0001, "lot_size": 100_000.0, "pip_value": 10.0},
    "BTCUSD": {"pip_size": 1.0,    "lot_size": 1.0,       "pip_value": 1.0},
    "ETHUSD": {"pip_size": 0.1,    "lot_size": 1.0,       "pip_value": 1.0},
    "US30":   {"pip_size": 1.0,    "lot_size": 1.0,       "pip_value": 1.0},
    "SPX500": {"pip_size": 0.25,   "lot_size": 1.0,       "pip_value": 1.0},
    "NASDAQ": {"pip_size": 0.25,   "lot_size": 1.0,       "pip_value": 1.0},
}

# Actions
ACTION_BUY  = 0
ACTION_SELL = 1
ACTION_HOLD = 2


# ---------------------------------------------------------------------------
# MACD calculation (pure Python, no talib dependency)
# ---------------------------------------------------------------------------

def _ema(values: List[float], period: int) -> List[float]:
    """Exponential moving average — pure Python."""
    if len(values) < period:
        return [0.0] * len(values)
    k = 2.0 / (period + 1)
    result = [0.0] * len(values)
    # Seed with SMA of first `period` values
    result[period - 1] = sum(values[:period]) / period
    for i in range(period, len(values)):
        result[i] = values[i] * k + result[i - 1] * (1 - k)
    return result


def _compute_macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[float, float]:
    """Return (macd_line, signal_line) for the last bar.

    Returns (0.0, 0.0) if not enough data.
    """
    if len(closes) < slow + signal:
        return 0.0, 0.0
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    # Only compute signal from valid (non-zero seed) part
    valid_macd = macd_line[slow - 1:]
    if len(valid_macd) < signal:
        return macd_line[-1], 0.0
    signal_line = _ema(valid_macd, signal)
    return macd_line[-1], signal_line[-1]


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class RLEnvironment:
    """Lightweight Gymnasium-compatible trading environment."""

    def __init__(
        self,
        candles: List[Dict[str, float]],
        symbol: str = "XAUUSD",
        initial_balance: float = 10_000.0,
        risk_pct: float = 1.0,
    ) -> None:
        self._candles = candles
        self._symbol = symbol
        self._initial_balance = initial_balance
        self._risk_pct = risk_pct
        cfg = self._get_symbol_config(symbol)
        self._pip_size: float = cfg["pip_size"]
        self._pip_value: float = cfg["pip_value"]
        self._lot_size: float = cfg["lot_size"]
        self._reset_state()

    @staticmethod
    def _get_symbol_config(symbol: str) -> Dict[str, float]:
        return SYMBOL_CONFIGS.get(
            symbol,
            {"pip_size": 0.0001, "lot_size": 100_000.0, "pip_value": 10.0},
        )

    def _reset_state(self) -> None:
        self._step = 50  # start with enough history for indicators
        self._balance: float = self._initial_balance
        self._position: int = 0       # -1 short, 0 flat, 1 long
        self._entry_price: float = 0.0
        self._equity_history: Deque[float] = deque([self._initial_balance], maxlen=10_000)
        self._obs_cache: Optional[List[float]] = None
        self._obs_cache_step: int = -1

    def reset(self) -> List[float]:
        self._reset_state()
        return self._get_observation()

    def _closes(self) -> List[float]:
        return [c["close"] for c in self._candles[: self._step + 1]]

    def _get_observation(self) -> List[float]:
        """Build observation vector. Cached per step to avoid recomputation."""
        if self._obs_cache_step == self._step and self._obs_cache is not None:
            return self._obs_cache

        closes = self._closes()
        n = len(closes)
        last = closes[-1] if n > 0 else 1.0

        # Returns (last 5)
        returns = []
        for i in range(1, min(6, n)):
            r = (closes[-i] - closes[-i - 1]) / (closes[-i - 1] or 1.0)
            returns.append(max(-1.0, min(1.0, r)))
        while len(returns) < 5:
            returns.append(0.0)

        # Moving averages (normalised by last price)
        ma_20 = (sum(closes[-20:]) / min(n, 20) / last) - 1.0 if n >= 20 else 0.0
        ma_50 = (sum(closes[-50:]) / min(n, 50) / last) - 1.0 if n >= 50 else 0.0

        # RSI (14)
        rsi = self._rsi(closes, 14)

        # MACD — real calculation (no longer placeholder)
        macd_val, macd_sig = _compute_macd(closes)
        macd_norm = math.tanh(macd_val / (last * 0.001 + 1e-9))  # normalise
        macd_sig_norm = math.tanh(macd_sig / (last * 0.001 + 1e-9))

        # Position encoding
        position_enc = float(self._position)  # -1, 0, 1

        # Unrealized PnL (normalised)
        unrealized = 0.0
        if self._position != 0 and self._entry_price > 0:
            unrealized = (
                (last - self._entry_price) * self._position / self._pip_size
            ) / (self._initial_balance or 1.0)
            unrealized = max(-1.0, min(1.0, unrealized))

        obs = returns + [
            ma_20, ma_50, rsi,
            macd_norm, macd_sig_norm,    # REAL MACD (not 0.0 anymore)
            position_enc, unrealized,
        ]

        self._obs_cache = obs
        self._obs_cache_step = self._step
        return obs

    @staticmethod
    def _rsi(closes: List[float], period: int = 14) -> float:
        """Wilder RSI, normalised to [-1, 1]."""
        if len(closes) < period + 1:
            return 0.0
        gains, losses = [], []
        for i in range(-period, 0):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 1.0
        rs = avg_gain / avg_loss
        rsi = 100.0 - 100.0 / (1.0 + rs)
        return (rsi / 50.0) - 1.0  # normalise to [-1, 1]

    def _calc_pnl(self, close_price: float) -> float:
        """Calculate P&L for closing a position."""
        if self._position == 0 or self._entry_price == 0:
            return 0.0
        pip_diff = (close_price - self._entry_price) * self._position / self._pip_size
        return pip_diff * self._pip_value

    def step(self, action: int) -> Tuple[List[float], float, bool, Dict]:
        """Execute one step."""
        candle = self._candles[self._step]
        price = candle["close"]
        reward = 0.0

        if action == ACTION_BUY and self._position != 1:
            if self._position == -1:
                reward = self._calc_pnl(price)
                self._balance += reward
            self._position = 1
            self._entry_price = price
            self._obs_cache = None  # invalidate cache

        elif action == ACTION_SELL and self._position != -1:
            if self._position == 1:
                reward = self._calc_pnl(price)
                self._balance += reward
            self._position = -1
            self._entry_price = price
            self._obs_cache = None

        elif action == ACTION_HOLD:
            # Include unrealized PnL in HOLD reward (encourages holding winners)
            if self._position != 0 and self._entry_price > 0:
                reward = self._calc_pnl(price) * 0.001  # small fraction

        self._step += 1
        self._equity_history.append(self._balance)

        done = self._step >= len(self._candles) - 1 or self._balance <= 0
        obs = self._get_observation()
        info = {
            "step": self._step,
            "balance": self._balance,
            "position": self._position,
            "price": price,
        }
        return obs, reward, done, info


# ---------------------------------------------------------------------------
# SB3 Gym wrapper (optional dependency)
# ---------------------------------------------------------------------------

try:
    import gymnasium as gym
    import numpy as np

    class SB3Env(gym.Env):
        """Gymnasium wrapper for stable-baselines3."""

        metadata = {"render_modes": []}

        def __init__(self, candles: List[Dict], symbol: str = "XAUUSD") -> None:
            super().__init__()
            self._env = RLEnvironment(candles, symbol)
            obs_size = 12  # 5 returns + ma20 + ma50 + rsi + macd + macd_sig + pos + unrealized
            self.observation_space = gym.spaces.Box(
                low=-2.0, high=2.0, shape=(obs_size,), dtype=np.float32
            )
            self.action_space = gym.spaces.Discrete(3)

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            obs = self._env.reset()
            return np.array(obs, dtype=np.float32), {}

        def step(self, action):
            obs, reward, done, info = self._env.step(int(action))
            return np.array(obs, dtype=np.float32), float(reward), done, False, info

    _HAS_GYM = True
except ImportError:
    _HAS_GYM = False
    logger.warning("gymnasium not available — RL agent will use rule-based fallback")


# ---------------------------------------------------------------------------
# RL Trading Agent
# ---------------------------------------------------------------------------

class RLTradingAgent:
    """PPO-trained RL agent with deterministic rule-based fallback."""

    def __init__(
        self,
        symbol: str = "XAUUSD",
        model_path: Optional[str] = None,
    ) -> None:
        self._symbol = symbol
        self._model = None
        self._env: Optional[RLEnvironment] = None

        if _HAS_GYM and model_path:
            try:
                from stable_baselines3 import PPO
                self._model = PPO.load(model_path)
                logger.info("RLAgent: loaded PPO model from %s", model_path)
            except Exception as exc:
                logger.warning("RLAgent: PPO load failed (%s) — using rule-based", exc)

    def predict(self, candles: List[Dict[str, float]]) -> Dict[str, Any]:
        """Return action dict: {action, confidence, reason}."""
        if not candles:
            return {"action": "HOLD", "confidence": 0.0, "reason": "no data"}

        self._env = RLEnvironment(candles, symbol=self._symbol)
        obs = self._env._get_observation()

        if self._model is not None:
            try:
                import numpy as np
                action, _ = self._model.predict(
                    np.array(obs, dtype=np.float32), deterministic=True
                )
                action_map = {ACTION_BUY: "BUY", ACTION_SELL: "SELL", ACTION_HOLD: "HOLD"}
                return {
                    "action": action_map.get(int(action), "HOLD"),
                    "confidence": 0.85,
                    "reason": "PPO model prediction",
                }
            except Exception as exc:
                logger.warning("RLAgent: PPO predict failed: %s", exc)

        # Deterministic rule-based fallback (not random)
        return self._rule_based(obs)

    @staticmethod
    def _rule_based(obs: List[float]) -> Dict[str, Any]:
        """Deterministic rule-based signal from observation vector.

        obs layout: [ret0..ret4, ma20, ma50, rsi, macd, macd_sig, position, unrealized]
        """
        if len(obs) < 12:
            return {"action": "HOLD", "confidence": 0.0, "reason": "insufficient obs"}

        rsi        = obs[7]   # normalised [-1, 1]; <-0.4 oversold, >0.4 overbought
        macd       = obs[8]
        macd_sig   = obs[9]
        ma20       = obs[5]
        ma50       = obs[6]
        position   = obs[10]

        # Trend: price above both MAs
        bullish_trend = ma20 > 0 and ma50 > 0
        bearish_trend = ma20 < 0 and ma50 < 0

        # MACD crossover
        macd_bullish = macd > macd_sig and macd > 0
        macd_bearish = macd < macd_sig and macd < 0

        # RSI filter
        oversold  = rsi < -0.4
        overbought = rsi > 0.4

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
            import numpy as np
            env = SB3Env(candles, self._symbol)
            model = PPO("MlpPolicy", env, verbose=0, seed=42)
            model.learn(total_timesteps=total_timesteps)
            if save_path:
                model.save(save_path)
                logger.info("RLAgent: model saved to %s", save_path)
            self._model = model
            return {
                "status": "trained",
                "timesteps": total_timesteps,
                "symbol": self._symbol,
                "save_path": save_path,
            }
        except Exception as exc:
            logger.error("RLAgent training failed: %s", exc)
            return {"error": str(exc)}
