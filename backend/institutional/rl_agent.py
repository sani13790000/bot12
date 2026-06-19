"""Reinforcement Learning Trading Agent — Gymnasium-compatible environment + PPO-ready."""

from __future__ import annotations
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ── Symbol configuration ─────────────────────────────────────────────────────
SYMBOL_CONFIGS: Dict[str, Dict] = {
    "XAUUSD": {"pip_size": 0.1,   "lot_size": 100.0,    "pip_value": 1.0},
    "XAGUSD": {"pip_size": 0.01,  "lot_size": 5000.0,   "pip_value": 1.0},
    "EURUSD": {"pip_size": 0.0001,"lot_size": 100000.0, "pip_value": 10.0},
    "GBPUSD": {"pip_size": 0.0001,"lot_size": 100000.0, "pip_value": 10.0},
    "USDJPY": {"pip_size": 0.01,  "lot_size": 100000.0, "pip_value": 9.09},
    "GBPJPY": {"pip_size": 0.01,  "lot_size": 100000.0, "pip_value": 9.09},
    "AUDUSD": {"pip_size": 0.0001,"lot_size": 100000.0, "pip_value": 10.0},
    "USDCAD": {"pip_size": 0.0001,"lot_size": 100000.0, "pip_value": 7.69},
    "USDCHF": {"pip_size": 0.0001,"lot_size": 100000.0, "pip_value": 11.0},
    "BTCUSD": {"pip_size": 1.0,   "lot_size": 1.0,      "pip_value": 1.0},
    "ETHUSD": {"pip_size": 0.1,   "lot_size": 1.0,      "pip_value": 1.0},
    "US30":   {"pip_size": 1.0,   "lot_size": 1.0,      "pip_value": 1.0},
    "NAS100": {"pip_size": 0.25,  "lot_size": 1.0,      "pip_value": 1.0},
    "USOIL":  {"pip_size": 0.01,  "lot_size": 1000.0,   "pip_value": 1.0},
}


def _get_symbol_config(symbol: str) -> Dict:
    """Return symbol config, defaulting to Forex minor if unknown."""
    sym = symbol.upper()
    if sym in SYMBOL_CONFIGS:
        return SYMBOL_CONFIGS[sym]
    # Auto-detect: JPY pairs, metals, indices
    if "JPY" in sym:
        return {"pip_size": 0.01, "lot_size": 100000.0, "pip_value": 9.09}
    if sym.startswith(("XAU", "XAG", "XPT", "XPD")):
        return {"pip_size": 0.1, "lot_size": 100.0, "pip_value": 1.0}
    if any(idx in sym for idx in ["30", "100", "500", "DAX", "GER", "UK", "NAS", "SPX"]):
        return {"pip_size": 1.0, "lot_size": 1.0, "pip_value": 1.0}
    if any(c in sym for c in ["BTC", "ETH", "LTC", "XRP"]):
        return {"pip_size": 1.0, "lot_size": 1.0, "pip_value": 1.0}
    # Default: Forex major
    return {"pip_size": 0.0001, "lot_size": 100000.0, "pip_value": 10.0}


@dataclass
class RLState:
    """Observation vector passed to the RL agent."""
    close: float
    open: float
    high: float
    low: float
    volume: float
    rsi_14: float
    atr_14: float
    ema_20: float
    ema_50: float
    macd: float
    macd_signal: float
    bb_upper: float
    bb_lower: float
    smc_score: float         # 0-100 from SMC engine
    pa_score: float          # 0-100 from PA engine
    ml_confidence: float     # 0-100 from ML engine
    position: int            # -1=short, 0=flat, 1=long
    unrealized_pnl: float
    equity_pct: float
    bars_in_trade: int


class RLEnvironment:
    """
    Custom trading environment compatible with Gymnasium interface.
    Supports any symbol via SYMBOL_CONFIGS.
    """

    ACTION_HOLD  = 0
    ACTION_BUY   = 1
    ACTION_SELL  = 2
    ACTION_CLOSE = 3

    def __init__(
        self,
        candles: List[Dict],
        symbol: str = "XAUUSD",
        initial_balance: float = 10_000.0,
        lot_size: float = 0.01,
        sl_pips: float = 50.0,
        max_bars_in_trade: int = 100,
        holding_penalty: float = 0.001,
    ):
        self._candles = candles
        self._symbol = symbol.upper()
        self._initial_balance = initial_balance
        self._lot_size = lot_size
        self._sl_pips = sl_pips
        self._max_bars_in_trade = max_bars_in_trade
        self._holding_penalty = holding_penalty

        # Symbol-aware config
        cfg = _get_symbol_config(self._symbol)
        self._pip_size: float = cfg["pip_size"]
        self._pip_value: float = cfg["pip_value"]

        # State
        self._balance = initial_balance
        self._cursor = 0
        self._position = 0
        self._entry_price = 0.0
        self._bars_in_trade = 0
        self._total_pnl = 0.0
        self._trades_count = 0
        self._wins = 0
        self._equity_history: List[float] = [initial_balance]

    def reset(self) -> List[float]:
        self._balance = self._initial_balance
        self._cursor = 50
        self._position = 0
        self._entry_price = 0.0
        self._bars_in_trade = 0
        self._total_pnl = 0.0
        self._trades_count = 0
        self._wins = 0
        self._equity_history = [self._initial_balance]
        return self._get_observation()

    def step(self, action: int) -> Tuple[List[float], float, bool, Dict]:
        if self._cursor >= len(self._candles) - 1:
            return self._get_observation(), 0.0, True, self._get_info()

        candle = self._candles[self._cursor]
        reward = 0.0

        if action == self.ACTION_BUY and self._position == 0:
            self._position = 1
            self._entry_price = candle["close"]
            self._bars_in_trade = 0

        elif action == self.ACTION_SELL and self._position == 0:
            self._position = -1
            self._entry_price = candle["close"]
            self._bars_in_trade = 0

        elif action == self.ACTION_CLOSE and self._position != 0:
            reward += self._close_position(candle["close"])

        if self._position != 0:
            self._bars_in_trade += 1
            reward -= self._holding_penalty

            next_candle = self._candles[min(self._cursor + 1, len(self._candles) - 1)]
            pnl = self._calc_pnl(next_candle["close"])
            if pnl <= -(self._sl_pips * self._pip_value * self._lot_size):
                reward += self._close_position(next_candle["close"])

            if self._bars_in_trade >= self._max_bars_in_trade:
                reward += self._close_position(candle["close"])

        current_equity = self._balance + (self._calc_pnl(candle["close"]) if self._position != 0 else 0)
        self._equity_history.append(current_equity)

        self._cursor += 1
        done = self._cursor >= len(self._candles) - 1
        return self._get_observation(), float(reward), done, self._get_info()

    def _close_position(self, price: float) -> float:
        pnl = self._calc_pnl(price)
        self._balance += pnl
        self._total_pnl += pnl
        self._trades_count += 1
        if pnl > 0:
            self._wins += 1
        self._position = 0
        self._entry_price = 0.0
        self._bars_in_trade = 0
        return pnl

    def _calc_pnl(self, price: float) -> float:
        """Symbol-aware P&L calculation."""
        if self._position == 0:
            return 0.0
        pip_diff = (price - self._entry_price) * self._position / self._pip_size
        return pip_diff * self._pip_value * self._lot_size

    def _get_observation(self) -> List[float]:
        idx = min(self._cursor, len(self._candles) - 1)
        c = self._candles[idx]
        close = c["close"]
        hist = self._candles[max(0, idx - 50):idx + 1]
        closes = [h["close"] for h in hist]

        rsi  = self._simple_rsi(closes, 14)
        atr  = self._simple_atr(hist, 14)
        ema20 = self._simple_ema(closes, 20)
        ema50 = self._simple_ema(closes, 50)

        unrealized = self._calc_pnl(close) if self._position != 0 else 0.0
        equity_pct = self._balance / self._initial_balance

        return [
            close, c.get("open", close), c.get("high", close), c.get("low", close),
            c.get("volume", 0.0),
            rsi / 100, atr, ema20, ema50,
            0.0, 0.0,  # macd placeholder
            close + atr * 2, close - atr * 2,  # bb_upper, bb_lower
            c.get("smc_score", 50.0) / 100,
            c.get("pa_score", 50.0) / 100,
            c.get("ml_confidence", 50.0) / 100,
            float(self._position), unrealized,
            equity_pct, float(self._bars_in_trade) / 100,
        ]

    def _get_info(self) -> Dict:
        return {
            "balance": self._balance,
            "total_pnl": self._total_pnl,
            "trades": self._trades_count,
            "win_rate": self._wins / self._trades_count * 100 if self._trades_count > 0 else 0,
            "position": self._position,
            "symbol": self._symbol,
            "pip_size": self._pip_size,
        }

    @staticmethod
    def _simple_rsi(closes: List[float], period: int) -> float:
        if len(closes) < period + 1:
            return 50.0
        gains = losses = 0.0
        for i in range(1, period + 1):
            d = closes[-i] - closes[-i - 1]
            if d > 0:
                gains += d
            else:
                losses -= d
        if losses == 0:
            return 100.0
        rs = gains / losses
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _simple_ema(closes: List[float], period: int) -> float:
        if not closes:
            return 0.0
        if len(closes) < period:
            return sum(closes) / len(closes)
        k = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for c in closes[period:]:
            ema = c * k + ema * (1 - k)
        return ema

    @staticmethod
    def _simple_atr(candles: List[Dict], period: int) -> float:
        if len(candles) < 2:
            return 1.0
        trs = []
        for i in range(1, len(candles)):
            hi = candles[i].get("high", candles[i]["close"])
            lo = candles[i].get("low",  candles[i]["close"])
            pc = candles[i - 1]["close"]
            trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
        return sum(trs[-period:]) / min(len(trs), period)


class RLTradingAgent:
    """
    RL Trading Agent wrapper.
    Uses RLEnvironment and provides train/predict interface.
    When stable-baselines3 is available, uses PPO.
    Otherwise, falls back to a simple rule-based policy.
    """

    ACTION_HOLD  = 0
    ACTION_BUY   = 1
    ACTION_SELL  = 2
    ACTION_CLOSE = 3

    def __init__(self, env: RLEnvironment):
        self._env = env
        self._model = None
        self._is_trained = False

    def train(self, total_timesteps: int = 50_000) -> Dict:
        """Train the RL agent. Uses PPO if available, else rule-based."""
        try:
            from stable_baselines3 import PPO
            import gymnasium as gym
            import numpy as np

            class SB3Env(gym.Env):
                def __init__(self, rl_env):
                    super().__init__()
                    self._rl = rl_env
                    self.observation_space = gym.spaces.Box(
                        low=-float("inf"), high=float("inf"),
                        shape=(20,), dtype=np.float32
                    )
                    self.action_space = gym.spaces.Discrete(4)

                def reset(self, seed=None, options=None):
                    obs = self._rl.reset()
                    return np.array(obs, dtype=np.float32), {}

                def step(self, action):
                    obs, reward, done, info = self._rl.step(int(action))
                    return np.array(obs, dtype=np.float32), reward, done, False, info

            sb3_env = SB3Env(self._env)
            self._model = PPO("MlpPolicy", sb3_env, verbose=0)
            self._model.learn(total_timesteps=total_timesteps)
            self._is_trained = True
            return {"method": "PPO", "timesteps": total_timesteps, "success": True,
                    "symbol": self._env._symbol, "pip_size": self._env._pip_size}

        except ImportError:
            self._is_trained = True
            return {"method": "rule_based_fallback", "timesteps": 0, "success": True,
                    "symbol": self._env._symbol, "pip_size": self._env._pip_size}

    def predict(self, observation: List[float]) -> int:
        """Predict action given observation vector."""
        if self._model is not None:
            try:
                import numpy as np
                action, _ = self._model.predict(np.array(observation, dtype="float32"))
                return int(action)
            except Exception:
                pass
        # Rule-based fallback
        smc_score = observation[13] * 100
        ml_conf   = observation[15] * 100
        position  = observation[16]
        if smc_score > 65 and ml_conf > 60 and position == 0:
            return self.ACTION_BUY if random.random() > 0.5 else self.ACTION_SELL
        return self.ACTION_HOLD
