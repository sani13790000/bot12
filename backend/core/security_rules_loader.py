"""
backend/core/security_rules_loader.py
Galaxy Vast AI — Security Rules Loader (repaired)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BUILTIN_RULES: list[dict[str, Any]] = [
    {"id": "RATE_LIMIT", "enabled": True, "threshold": 100, "window_s": 60},
    {"id": "IP_BLOCK", "enabled": True, "max_strikes": 5},
    {"id": "JWT_EXPIRY", "enabled": True, "max_age_s": 3600},
    {"id": "INJECT_DETECT", "enabled": True},
    {"id": "CORS_STRICT", "enabled": True},
]


class SecurityRulesLoader:
    def __init__(self, rules_file: str | None = None) -> None:
        self._rules: list[dict[str, Any]] = list(_BUILTIN_RULES)
        if rules_file:
            self._load_file(Path(rules_file))

    def _load_file(self, path: Path) -> None:
        try:
            extra = json.loads(path.read_text())
            if isinstance(extra, list):
                self._rules.extend(extra)
                logger.info("Loaded %d extra rules from %s", len(extra), path)
        except Exception as exc:
            logger.warning("Could not load rules from %s: %s", path, exc)

    def get_rules(self) -> list[dict[str, Any]]:
        return [r for r in self._rules if r.get("enabled", True)]

    def get_rule(self, rule_id: str) -> dict[str, Any] | None:
        for r in self._rules:
            if r.get("id") == rule_id:
                return r
        return None

    def disable_rule(self, rule_id: str) -> bool:
        for r in self._rules:
            if r.get("id") == rule_id:
                r["enabled"] = False
                return True
        return False


_loader: SecurityRulesLoader | None = None


def get_security_rules() -> SecurityRulesLoader:
    global _loader
    if _loader is None:
        _loader = SecurityRulesLoader()
    return _loader


__all__ = ["SecurityRulesLoader", "get_security_rules"]
