"""
backend/core/security_rules_loader.py
Phase-5 - Security Rule Engine loader
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)
_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "security_rules.json")


@dataclass
class SecurityRule:
    rule_id: str
    name: str
    condition: str
    action: str
    severity: str = "medium"
    enabled: bool = True


class SecurityRulesLoader:
    """Loads and reloads security rules from JSON file."""

    def __init__(self, path: str = _DEFAULT_PATH, reload_interval: float = 60.0) -> None:
        self._path = path
        self._reload_interval = reload_interval
        self._rules: Dict[str, SecurityRule] = {}
        self._last_loaded: float = 0.0
        self._lock = asyncio.Lock()

    async def load(self) -> Dict[str, SecurityRule]:
        async with self._lock:
            now = time.time()
            if now - self._last_loaded < self._reload_interval and self._rules:
                return self._rules
            try:
                with open(self._path) as fh:
                    raw = json.load(fh)
                self._rules = {r["rule_id"]: SecurityRule(**r) for r in raw.get("rules", [])}
                self._last_loaded = now
                log.debug("Loaded %d security rules from %s", len(self._rules), self._path)
            except FileNotFoundError:
                log.debug("Security rules file not found: %s", self._path)
            except Exception as exc:
                log.error("Failed to load security rules: %s", exc)
            return self._rules

    def update_rules(self, rules: Dict[str, Any]) -> None:
        for rule_id, rule_data in rules.items():
            self._rules[rule_id] = SecurityRule(**rule_data)
        log.info("Updated %d security rules", len(rules))

    async def get_rule(self, rule_id: str) -> Optional[SecurityRule]:
        await self.load()
        return self._rules.get(rule_id)


_loader: Optional[SecurityRulesLoader] = None


def get_security_rules_loader() -> SecurityRulesLoader:
    global _loader
    if _loader is None:
        _loader = SecurityRulesLoader()
    return _loader
