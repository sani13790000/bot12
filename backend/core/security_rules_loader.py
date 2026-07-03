"""
backend/core/security_rules_loader.py
Phase-5 — Security Rule Engine loader.
Loads YAML/JSON security rules at startup.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class SecurityRule:
    rule_id: str
    name: str
    description: str
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    enabled: bool = True
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SecurityRuleSet:
    version: str
    rules: List[SecurityRule] = field(default_factory=list)

    def get_rule(self, rule_id: str) -> Optional[SecurityRule]:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def get_enabled(self, severity: Optional[str] = None) -> List[SecurityRule]:
        rules = [r for r in self.rules if r.enabled]
        if severity:
            rules = [r for r in rules if r.severity == severity]
        return rules


class SecurityRulesLoader:
    """Loads and manages security rules from config."""

    def __init__(self, rules_path: Optional[str] = None) -> None:
        self._path  = rules_path or os.environ.get("SECURITY_RULES_PATH", "")
        self._rules: Optional[SecurityRuleSet] = None

    def load(self) -> SecurityRuleSet:
        if self._rules:
            return self._rules

        if self._path and Path(self._path).exists():
            try:
                raw = Path(self._path).read_text(encoding="utf-8")
                data = json.loads(raw)
                rules = [SecurityRule(**r) for r in data.get("rules", [])]
                self._rules = SecurityRuleSet(version=data.get("version", "1.0"), rules=rules)
                log.info("security_rules_loaded rules=%d", len(rules))
                return self._rules
            except Exception as exc:
                log.warning("security_rules_load_error: %s", exc)

        # Default empty ruleset
        self._rules = SecurityRuleSet(version="1.0", rules=[])
        return self._rules


_loader = SecurityRulesLoader()


def get_security_rules() -> SecurityRuleSet:
    return _loader.load()
