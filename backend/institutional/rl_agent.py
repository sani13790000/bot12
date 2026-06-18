"""Galaxy Vast AI Trading Platform — Reinforcement Learning Trading Agent.

Architecture:
- Gymnasium environment wrapping OHLC data
- Stable-Baselines3 PPO agent
- Train / predict / persist / reload
- Action space: [HOLD, BUY, SELL]
"""
from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from backend.research.backtest.engine import CandleData


@dataclass
class RLAgentConfig:
    symbol: str = "XAUUSD"
    window_size: int = 20
    initial_balance: float = 100_000.0
    position_size: float = 0.1
    commission: float = 3.5
    spread: float = 0.2
    total_timesteps: int = 50_000
    model_path: str = "models/rl_ppo_galaxyvast"


class TradingEnv(gym.Env):
    """Custom Gymnasium environment for RL trading."""

    metadata = {"render_modes": ["human"]}

    def __init__(self, candles: List[CandleData], config: RLAgentConfig):
        super().__init__()
        self.candles = candles
        self.config = config
        self.window_size = config.window_size
        self.action_space = spaces.Discrete(3)  # 0=HOLD, 1=BUY, 2=SELL
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(self.window_size * 5 + 3,),
            dtype=np.float32,
        )
        self.position = 0  # -1=SHORT, 0=FLAT, 1=LONG
        self.entry_price = 0.0
        self.balance = config.initial_balance
        self.current_step = self.window_size
        self.max_steps = len(candles) - 1

    def reset(self, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None):
        super().reset(seed=seed)
        self.position = 0
        self.entry_price = 0.0
        self.balance = self.config.initial_balance
        self.current_step = self.window_size
        return self._get_observation(), {}

    def step(self, action: int):
        reward = 0.0
        done = False
        truncated = False
        candle = self.candles[self.current_step]

        # Close existing position first
        if self.position == 1 and action == 2:
            reward = self._close_trade(candle.close)
        elif self.position == -1 and action == 1:
            reward = self._close_trade(candle.close)

        # Open new position
        if self.position == 0 and action in (1, 2):
            self.position = 1 if action == 1 else -1
            self.entry_price = candle.close

        self.current_step += 1
        if self.current_step >= self.max_steps:
            done = True
            if self.position != 0:
                reward += self._close_trade(self.candles[self.current_step].close)

        obs = self._get_observation()
        return obs, reward, done, truncated, {}

    def _close_trade(self, exit_price: float) -> float:
        if self.position == 0 or self.entry_price == 0:
            return 0.0
        spread_cost = self.config.spread * 0.1
        pnl = (exit_price - self.entry_price - spread_cost) * self.config.position_size
        if self.position == -1:
            pnl = -pnl
        self.balance += pnl - self.config.commission
        self.position = 0
        self.entry_price = 0.0
        return pnl

    def _get_observation(self) -> np.ndarray:
        window = self.candles[self.current_step - self.window_size:self.current_step]
        features = []
        for c in window:
            features.extend([c.open, c.high, c.low, c.close, c.volume])
        features.extend([self.position, self.balance / self.config.initial_balance, self.entry_price / 1000.0])
        return np.array(features, dtype=np.float32)


class RLTradingAgent:
    """Reinforcement Learning trading agent using PPO."""

    def __init__(self, config: Optional[RLAgentConfig] = None):
        self.config = config or RLAgentConfig()
        self._model = None
        self._env = None

    def build_env(self, candles: List[CandleData]) -> TradingEnv:
        self._env = TradingEnv(candles, self.config)
        return self._env

    def train(self, candles: List[CandleData], timesteps: Optional[int] = None) -> Dict[str, Any]:
        try:
            from stable_baselines3 import PPO
        except ImportError as exc:
            raise RuntimeError("stable-baselines3 is required for RL training") from exc

        env = self.build_env(candles)
        self._model = PPO(
            "MlpPolicy",
            env,
            verbose=0,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
        )
        steps = timesteps or self.config.total_timesteps
        self._model.learn(total_timesteps=steps)

        os.makedirs(os.path.dirname(self.config.model_path) or ".", exist_ok=True)
        self._model.save(self.config.model_path)
        return {"status": "trained", "timesteps": steps, "model_path": self.config.model_path}

    def predict(self, candles: List[CandleData]) -> int:
        if self._model is None:
            self.load()
        env = self.build_env(candles)
        obs, _ = env.reset()
        action, _ = self._model.predict(obs, deterministic=True)
        return int(action)

    def load(self, path: Optional[str] = None) -> None:
        try:
            from stable_baselines3 import PPO
        except ImportError as exc:
            raise RuntimeError("stable-baselines3 is required") from exc

        target = path or self.config.model_path
        if not os.path.exists(target + ".zip"):
            raise FileNotFoundError(f"RL model not found at {target}")
        self._model = PPO.load(target)

    def save_metadata(self, metadata: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.config.model_path) or ".", exist_ok=True)
        with open(self.config.model_path + "_meta.pkl", "wb") as f:
            pickle.dump(metadata, f)

    def load_metadata(self) -> Dict[str, Any]:
        meta_path = self.config.model_path + "_meta.pkl"
        if not os.path.exists(meta_path):
            return {}
        with open(meta_path, "rb") as f:
            return pickle.load(f)
