"""
backend/core/security_rules_loader.py
Phase-5 -- Security Rules Loader
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
DEFAULT_RULES_PATH = Path(os.getenv("SECURITY_RULES_PATH", "/etc/bot12/security_rules.json"))


class SecurityRulesLoader:
    """Load and manage security rules from configuration files."""

    def __init__(self, rules_path: Path = DEFAULT_RULES_PATH) -> None:
        self._path   = rules_path
        self._rules: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            logger.warning("Rules file not found: %s -- using defaults", self._path)
            self._rules = self._default_rules()
        else:
            with open(self._path, encoding="utf-8") as fh:
                self._rules = json.load(fh)
            logger.info("Loaded security rules from %s", self._path)
        self._loaded = True
        return self._rules

    def get(self, key: str, default: Any = None) -> Any:
        if not self._loaded:
            self.load()
        return self._rules.get(key, default)

    def reload(self) -> dict[str, Any]:
        self._loaded = False
        return self.load()

    @staticmethod
    def _default_rules() -> dict[str, Any]:
        return {
            "max_position_size": 0.02,
            "max_daily_loss": 0.05,
            "max_drawdown": 0.10,
            "allowed_symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
            "require_sl": True,
            "require_tp": False,
            "min_rr_ratio": 1.5,
        }


rules_loader = SecurityRulesLoader()
