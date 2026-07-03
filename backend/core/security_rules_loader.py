"""
backend/core/security_rules_loader.py
Phase-5 Security Rules Loader
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RULES: dict[str, Any] = {
    "rate_limit": {"requests_per_minute": 60, "burst": 10},
    "auth": {"max_failed_attempts": 5, "lockout_minutes": 15},
    "cors": {"allowed_origins": ["http://localhost:3000"]},
    "injection": {"enabled": True, "patterns": ["sql", "xss", "path_traversal"]},
}


class SecurityRulesLoader:
    """Loads and validates security rules from JSON or defaults."""

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self._path = Path(rules_path) if rules_path else None
        self._rules: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        if self._path and self._path.exists():
            try:
                with open(self._path) as f:
                    loaded = json.load(f)
                self._rules = {**DEFAULT_RULES, **loaded}
                logger.info(f"Security rules loaded from {self._path}")
            except Exception as e:
                logger.warning(f"Failed to load rules from {self._path}: {e}; using defaults")
                self._rules = dict(DEFAULT_RULES)
        else:
            self._rules = dict(DEFAULT_RULES)
        return self._rules

    def get(self, key: str, default: Any = None) -> Any:
        if not self._rules:
            self.load()
        return self._rules.get(key, default)

    def reload(self) -> dict[str, Any]:
        self._rules = {}
        return self.load()


_loader: SecurityRulesLoader | None = None


def get_security_rules() -> SecurityRulesLoader:
    global _loader
    if _loader is None:
        rules_path = os.environ.get("SECURITY_RULES_PATH")
        _loader = SecurityRulesLoader(rules_path)
        _loader.load()
    return _loader


__all__ = ["SecurityRulesLoader", "get_security_rules", "DEFAULT_RULES"]
