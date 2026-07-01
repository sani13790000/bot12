"""
backend/core/security_rules_loader.py
Phase-5 — Security Rule Engine loader

Reads backend/core/security_rules.yaml (or .json) and exposes typed rules.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)
__all__ = ["SecurityRulesLoader", "get_security_rules"]

_DEFAULT_RULES: Dict[str, Any] = {
    "max_login_attempts": 5,
    "session_timeout_minutes": 60,
    "require_2fa": False,
    "allowed_ip_ranges": [],
    "rate_limit_requests_per_minute": 100,
}


class SecurityRulesLoader:
    def __init__(self, rules_path: Optional[str] = None) -> None:
        self._rules: Dict[str, Any] = dict(_DEFAULT_RULES)
        if rules_path and Path(rules_path).exists():
            try:
                self._rules.update(json.loads(Path(rules_path).read_text()))
            except Exception as exc:
                logger.warning("Could not load security rules from %s: %s", rules_path, exc)

    def get(self, key: str, default: Any = None) -> Any:
        return self._rules.get(key, default)

    def all(self) -> Dict[str, Any]:
        return dict(self._rules)


from typing import Optional
_loader: Optional[SecurityRulesLoader] = None

def get_security_rules() -> SecurityRulesLoader:
    global _loader
    if _loader is None:
        _loader = SecurityRulesLoader()
    return _loader
