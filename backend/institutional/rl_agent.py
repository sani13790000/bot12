"""
backend/institutional/rl_agent.py
Reinforcement Learning agent for institutional trading.
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RLState:
    """RL environment state."""
    price: float
    volume: float
    volatility: float
    positions_open: int
    equity: float
    margin_level: float


class RLTradingAgent:
    """Reinforcement Learning trading agent."""

    def __init__(
        self,
        state_size: int = 6,
        action_size: int = 3,  # BUY, SELL, HOLD
        learning_rate: float = 0.01,
    ):
        self.state_size = state_size
        self.action_size = action_size
        self.learning_rate = learning_rate
        self.q_table = {}
        logger.info("[rl_agent] Initialized with state_size=%d, action_size=%d", state_size, action_size)

    def choose_action(
        self,
        state: RLState,
        epsilon: float = 0.1
    ) -> str:
        """
        Choose action using epsilon-greedy policy.

        Args:
            state: Current environment state
            epsilon: Exploration rate

        Returns:
            Action: 'BUY', 'SELL', or 'HOLD'
        """
        state_key = self._state_to_key(state)
        
        if np.random.random() < epsilon:
            # Explore
            action = np.random.choice(['BUY', 'SELL', 'HOLD'])
        else:
            # Exploit
            if state_key not in self.q_table:
                self.q_table[state_key] = [0, 0, 0]  # Q-values for BUY, SELL, HOLD
            
            q_values = self.q_table[state_key]
            action = ['BUY', 'SELL', 'HOLD'][np.argmax(q_values)]
        
        logger.debug("[rl_agent] Action chosen: %s for state: %s", action, state_key)
        return action

    def learn(
        self,
        state: RLState,
        action: str,
        reward: float,
        next_state: RLState,
        done: bool
    ) -> None:
        """
        Update Q-value using Q-learning.

        Args:
            state: Starting state
            action: Action taken
            reward: Reward received
            next_state: Resulting state
            done: Episode finished
        """
        state_key = self._state_to_key(state)
        next_state_key = self._state_to_key(next_state)
        action_idx = {'BUY': 0, 'SELL': 1, 'HOLD': 2}[action]
        
        # Initialize Q-values if needed
        if state_key not in self.q_table:
            self.q_table[state_key] = [0, 0, 0]
        if next_state_key not in self.q_table:
            self.q_table[next_state_key] = [0, 0, 0]
        
        # Q-learning update
        old_q = self.q_table[state_key][action_idx]
        max_next_q = max(self.q_table[next_state_key])
        new_q = old_q + self.learning_rate * (reward + (0 if done else 0.99 * max_next_q) - old_q)
        
        self.q_table[state_key][action_idx] = new_q
        logger.debug("[rl_agent] Learned: old_q=%.4f, new_q=%.4f, reward=%.2f", old_q, new_q, reward)

    @staticmethod
    def _state_to_key(state: RLState) -> str:
        """Convert state to hashable key."""
        return (
            f"{state.price:.2f}_"
            f"{state.volume:.0f}_"
            f"{state.volatility:.4f}_"
            f"{state.positions_open}_"
            f"{state.equity:.0f}_"
            f"{state.margin_level:.2f}"
        )
