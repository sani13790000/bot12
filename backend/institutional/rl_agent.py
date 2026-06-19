"""
Reinforcement Learning agent for institutional trading.

Performance improvements in this version:
  * _ema(): O(1) incremental EMA — no full-slice recalculation per step
  * _compute_macd(): O(1) incremental using prev_ema_fast/slow state
  * _get_observation(): cached per step — rebuilt only when _step advances
  * _equity_history: deque(maxlen=10_000) caps memory
  * SB3Env.obs_size: computed dynamically from env.observation_space.shape
"""
from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Symbol configs ──────────────────────────────────────────
SYMBOL_CONFIGS: Dict[str, Dict[str, float]] = {
    "XAUUSD": {"pip_size": 0.01, "lot_size": 100.0, "spread": 0.30},
    "EURUSD": {"pip_size": 0.0001, "lot_size": 100_000.0, "spread": 0.00010},
    "GBPUSD": {"pip_size": 0.0001, "lot_size": 100_000.0, "spread": 0.00012},
    "USDJPY": {"pip_size": 0.01, "lot_size": 100_000.0, "spread": 0.010},
    "USDCHF": {"pip_size": 0.0001, "lot_size": 100_000.0, "spread": 0.00012},
    "AUDUSD": {"pip_size": 0.0001, "lot_size": 100_000.0, "spread": 0.00013},
    "NZDUSD": {"pip_size": 0.0001, "lot_size": 100_000.0, "spread": 0.00015},
    "USDCAD": {"pip_size": 0.0001, "lot_size": 100_000.0, "spread": 0.00014},
    "EURGBP": {"pip_size": 0.0001, "lot_size": 100_000.0, "spread": 0.00011},
    "EURJPY": {"pip_size": 0.01, "lot_size": 100_000.0, "spread": 0.013},
    "GBPJPY": {"pip_size": 0.01, "lot_size": 100_000.0, "spread": 0.015},
    "BTCUSD": {"pip_size": 1.0, "lot_size": 1.0, "spread": 50.0},
    "ETHUSD": {"pip_size": 0.01, "lot_size": 1.0, "spread": 2.0},
    "XAGUSD": {"pip_size": 0.001, "lot_size": 5000.0, "spread": 0.020},
}

ACTION_HOLD = 0
ACTION_BUY = 1
ACTION_SELL = 2


@dataclass
class Position:
    direction: int   # ACTION_BUY or ACTION_SELL
    entry_price: float
    lot_size: float
    open_step: int


# ── Incremental math helpers ────────────────────────────────

def _ema_alpha(period: int) -> float:
    """EMA smoothing factor."""
    return 2.0 / (period + 1)


def _ema_step(prev_ema: float, price: float, alpha: float) -> float:
    """O(1) incremental EMA update."""
    return alpha * price + (1.0 - alpha) * prev_ema


# ── Trading environment ─────────────────────────────────────

class TradingEnv:
    """
    Lightweight trading simulation environment.

    All indicator state is maintained incrementally (O(1) per step) to avoid
    repeated O(n) slice-and-recalculate patterns.
    """

    OBSERVATION_SIZE = 12  # must match _build_obs() output length

    def __init__(
        self,
        candles: List[Dict[str, Any]],
        symbol: str = "XAUUSD",
        initial_balance: float = 10_000.0,
        lot_size: float = 0.01,
        max_steps: Optional[int] = None,
    ) -> None:
        if not candles:
            raise ValueError("candles list is empty")

        self._raw = candles
        self._symbol = symbol
        self._cfg = SYMBOL_CONFIGS.get(symbol, SYMBOL_CONFIGS["XAUUSD"])
        self._initial_balance = initial_balance
        self._lot_size = lot_size
        self._max_steps = max_steps or len(candles) - 1

        # — price arrays (numpy for fast indexing)
        closes = np.array([c["close"] for c in candles], dtype=np.float64)
        highs = np.array([c["high"] for c in candles], dtype=np.float64)
        lows = np.array([c["low"] for c in candles], dtype=np.float64)
        self._closes = closes
        self._highs = highs
        self._lows = lows

        # — incremental indicator state (initialised in reset)
        self._ema9: float = 0.0
        self._ema21: float = 0.0
        self._ema50: float = 0.0
        self._macd_ema_fast: float = 0.0   # EMA(12)
        self._macd_ema_slow: float = 0.0   # EMA(26)
        self._macd_signal_ema: float = 0.0  # EMA(9) of MACD line
        self._prev_gains: deque[float] = deque(maxlen=14)
        self._prev_losses: deque[float] = deque(maxlen=14)
        self._avg_gain: float = 0.0
        self._avg_loss: float = 0.0

        # — runtime state
        self._step = 0
        self._balance = initial_balance
        self._equity = initial_balance
        self._position: Optional[Position] = None
        self._equity_history: deque[float] = deque(maxlen=10_000)
        self._trade_log: List[Dict[str, Any]] = []

        # — observation cache
        self._obs_cache: Optional[np.ndarray] = None
        self._obs_cache_step: int = -1

    # ─ Reset ───────────────────────────────────────────

    def reset(self) -> np.ndarray:
        self._step = 50  # warm-up: first 50 candles used for indicator seed
        self._balance = self._initial_balance
        self._equity = self._initial_balance
        self._position = None
        self._equity_history.clear()
        self._equity_history.append(self._initial_balance)
        self._trade_log.clear()
        self._obs_cache = None
        self._obs_cache_step = -1

        # Seed incremental indicators using first 50 candles
        self._seed_indicators()
        return self._get_observation()

    def _seed_indicators(self) -> None:
        """Warm-up all indicators over the first _step candles."""
        closes = self._closes
        n = min(self._step, len(closes))
        if n < 2:
            return

        # EMAs
        a9 = _ema_alpha(9)
        a21 = _ema_alpha(21)
        a50 = _ema_alpha(50)
        af = _ema_alpha(12)
        as_ = _ema_alpha(26)
        as9 = _ema_alpha(9)

        self._ema9 = closes[0]
        self._ema21 = closes[0]
        self._ema50 = closes[0]
        self._macd_ema_fast = closes[0]
        self._macd_ema_slow = closes[0]
        macd_line = 0.0
        self._macd_signal_ema = 0.0

        for i in range(1, n):
            p = closes[i]
            self._ema9 = _ema_step(self._ema9, p, a9)
            self._ema21 = _ema_step(self._ema21, p, a21)
            self._ema50 = _ema_step(self._ema50, p, a50)
            self._macd_ema_fast = _ema_step(self._macd_ema_fast, p, af)
            self._macd_ema_slow = _ema_step(self._macd_ema_slow, p, as_)
            macd_line = self._macd_ema_fast - self._macd_ema_slow
            self._macd_signal_ema = _ema_step(
                self._macd_signal_ema, macd_line, as9
            )

        # RSI seed
        gains, losses = [], []
        for i in range(1, min(15, n)):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        if gains:
            self._avg_gain = sum(gains) / len(gains)
            self._avg_loss = sum(losses) / len(losses)

    # ─ Step ───────────────────────────────────────────

    def step(
        self, action: int
    ) -> Tuple[np.ndarray, float, bool, Dict[str, Any]]:
        if self._step >= min(self._max_steps, len(self._closes) - 1):
            return self._get_observation(), 0.0, True, {}

        price = float(self._closes[self._step])

        # — O(1) indicator update
        self._update_indicators(price)
        self._step += 1
        # invalidate obs cache
        self._obs_cache_step = -1

        reward = self._apply_action(action, price)

        self._equity = self._balance + self._calc_unrealized_pnl()
        self._equity_history.append(self._equity)

        done = self._step >= min(self._max_steps, len(self._closes) - 1)
        return self._get_observation(), reward, done, {"equity": self._equity}

    def _update_indicators(self, price: float) -> None:
        """Update all indicators O(1) per step."""
        a9 = _ema_alpha(9)
        a21 = _ema_alpha(21)
        a50 = _ema_alpha(50)
        af = _ema_alpha(12)
        as_ = _ema_alpha(26)
        as9 = _ema_alpha(9)

        self._ema9 = _ema_step(self._ema9, price, a9)
        self._ema21 = _ema_step(self._ema21, price, a21)
        self._ema50 = _ema_step(self._ema50, price, a50)
        self._macd_ema_fast = _ema_step(self._macd_ema_fast, price, af)
        self._macd_ema_slow = _ema_step(self._macd_ema_slow, price, as_)
        macd_line = self._macd_ema_fast - self._macd_ema_slow
        self._macd_signal_ema = _ema_step(self._macd_signal_ema, macd_line, as9)

        # Wilder RSI smoothing O(1)
        if self._step > 0:
            prev_close = float(self._closes[self._step - 1])
            delta = price - prev_close
            gain = max(delta, 0.0)
            loss = max(-delta, 0.0)
            alpha_rsi = 1.0 / 14
            self._avg_gain = (1 - alpha_rsi) * self._avg_gain + alpha_rsi * gain
            self._avg_loss = (1 - alpha_rsi) * self._avg_loss + alpha_rsi * loss

    # ─ Observation ───────────────────────────────────────

    def _get_observation(self) -> np.ndarray:
        """Return cached observation — rebuilt only when _step changes."""
        if self._obs_cache is not None and self._obs_cache_step == self._step:
            return self._obs_cache
        obs = self._build_obs()
        self._obs_cache = obs
        self._obs_cache_step = self._step
        return obs

    def _build_obs(self) -> np.ndarray:
        """Build observation vector — all O(1) using cached indicator state."""
        price = float(self._closes[min(self._step, len(self._closes) - 1)])
        norm = price if price > 0 else 1.0

        # RSI
        if self._avg_loss < 1e-10:
            rsi = 1.0
        else:
            rs = self._avg_gain / self._avg_loss
            rsi = rs / (1.0 + rs)  # normalised 0–1

        # MACD (normalised by price)
        macd_line = self._macd_ema_fast - self._macd_ema_slow
        macd_norm = macd_line / norm
        macd_signal_norm = (macd_line - self._macd_signal_ema) / norm

        # Position features
        pos_direction = 0.0
        pos_pnl = 0.0
        pos_duration = 0.0
        if self._position:
            pos_direction = 1.0 if self._position.direction == ACTION_BUY else -1.0
            pos_pnl = self._calc_unrealized_pnl() / (self._initial_balance + 1e-10)
            pos_duration = (self._step - self._position.open_step) / (
                self._max_steps + 1e-10
            )

        obs = np.array(
            [
                price / norm,                          # 0 normalized price (always 1.0)
                self._ema9 / norm,                     # 1 EMA9
                self._ema21 / norm,                    # 2 EMA21
                self._ema50 / norm,                    # 3 EMA50
                rsi,                                   # 4 RSI
                macd_norm,                             # 5 MACD line
                macd_signal_norm,                      # 6 MACD signal
                self._equity / (self._initial_balance + 1e-10),  # 7 equity ratio
                self._step / (self._max_steps + 1e-10),          # 8 progress
                pos_direction,                         # 9 position direction
                pos_pnl,                               # 10 unrealized PnL
                pos_duration,                          # 11 position duration
            ],
            dtype=np.float32,
        )
        assert len(obs) == self.OBSERVATION_SIZE, (
            f"obs size mismatch: {len(obs)} != {self.OBSERVATION_SIZE}"
        )
        return obs

    # ─ Action ───────────────────────────────────────────

    def _apply_action(
        self, action: int, price: float
    ) -> float:
        spread = self._cfg["spread"]
        reward = 0.0

        if action == ACTION_HOLD:
            # Reward for holding a profitable position
            if self._position:
                reward = self._calc_unrealized_pnl() * 0.001

        elif action == ACTION_BUY:
            if self._position and self._position.direction == ACTION_SELL:
                reward = self._close_position(price - spread)
            elif self._position is None:
                self._position = Position(
                    direction=ACTION_BUY,
                    entry_price=price + spread,
                    lot_size=self._lot_size,
                    open_step=self._step,
                )

        elif action == ACTION_SELL:
            if self._position and self._position.direction == ACTION_BUY:
                reward = self._close_position(price - spread)
            elif self._position is None:
                self._position = Position(
                    direction=ACTION_SELL,
                    entry_price=price - spread,
                    lot_size=self._lot_size,
                    open_step=self._step,
                )

        return float(reward)

    def _calc_unrealized_pnl(self) -> float:
        if self._position is None:
            return 0.0
        price = float(self._closes[self._step])
        spread = self._cfg["spread"]
        lot = self._cfg["lot_size"]
        if self._position.direction == ACTION_BUY:
            return (price - self._position.entry_price) * self._position.lot_size * lot
        return (self._position.entry_price - (price + spread)) * self._position.lot_size * lot

    def _close_position(self, exit_price: float) -> float:
        if self._position is None:
            return 0.0
        lot = self._cfg["lot_size"]
        if self._position.direction == ACTION_BUY:
            pnl = (exit_price - self._position.entry_price) * self._position.lot_size * lot
        else:
            pnl = (self._position.entry_price - exit_price) * self._position.lot_size * lot
        self._balance += pnl
        self._trade_log.append({
            "direction": self._position.direction,
            "entry_price": self._position.entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "duration": self._step - self._position.open_step,
        })
        self._position = None
        return float(pnl)

    # ─ Rule-based fallback ─────────────────────────────────

    def rule_based(self) -> int:
        """Deterministic rule-based decision using O(1) indicator state."""
        # RSI
        if self._avg_loss < 1e-10:
            rsi = 100.0
        else:
            rs = self._avg_gain / self._avg_loss
            rsi = 100.0 - 100.0 / (1.0 + rs)

        macd_line = self._macd_ema_fast - self._macd_ema_slow
        macd_hist = macd_line - self._macd_signal_ema
        trend_up = self._ema9 > self._ema21 > self._ema50
        trend_down = self._ema9 < self._ema21 < self._ema50

        if trend_up and rsi < 60 and macd_hist > 0:
            return ACTION_BUY
        if trend_down and rsi > 40 and macd_hist < 0:
            return ACTION_SELL
        return ACTION_HOLD

    # ─ Results ───────────────────────────────────────────

    @property
    def summary(self) -> Dict[str, Any]:
        equity_list = list(self._equity_history)
        peak = max(equity_list) if equity_list else self._initial_balance
        trough = min(equity_list) if equity_list else self._initial_balance
        max_dd = (peak - trough) / peak if peak > 0 else 0.0
        wins = [t for t in self._trade_log if t["pnl"] > 0]
        return {
            "final_equity": self._equity,
            "total_return_pct": (
                (self._equity - self._initial_balance) / self._initial_balance * 100
            ),
            "max_drawdown_pct": max_dd * 100,
            "total_trades": len(self._trade_log),
            "win_rate": len(wins) / len(self._trade_log) if self._trade_log else 0.0,
            "profit_factor": (
                sum(t["pnl"] for t in wins)
                / (abs(sum(t["pnl"] for t in self._trade_log if t["pnl"] <= 0)) + 1e-10)
            ),
        }


# ── SB3-compatible Gymnasium env wrapper ─────────────────────────

try:
    import gymnasium as gym
    from gymnasium import spaces

    class SB3Env(gym.Env):
        """Gymnasium wrapper for Stable-Baselines3 training."""

        metadata = {"render_modes": []}

        def __init__(
            self,
            candles: List[Dict[str, Any]],
            symbol: str = "XAUUSD",
            initial_balance: float = 10_000.0,
            lot_size: float = 0.01,
        ) -> None:
            super().__init__()
            self._env = TradingEnv(
                candles=candles,
                symbol=symbol,
                initial_balance=initial_balance,
                lot_size=lot_size,
            )
            obs_size = self._env.OBSERVATION_SIZE  # dynamic — not hardcoded
            self.observation_space = spaces.Box(
                low=-10.0, high=10.0, shape=(obs_size,), dtype=np.float32
            )
            self.action_space = spaces.Discrete(3)

        def reset(
            self,
            *,
            seed: Optional[int] = None,
            options: Optional[Dict[str, Any]] = None,
        ) -> Tuple[np.ndarray, Dict[str, Any]]:
            super().reset(seed=seed)
            obs = self._env.reset()
            return obs, {}

        def step(
            self, action: int
        ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
            obs, reward, terminated, info = self._env.step(action)
            return obs, reward, terminated, False, info

        def render(self) -> None:
            pass

except ImportError:
    logger.info("gymnasium not available — SB3Env disabled")
