"""
backend/core/security_rules_loader.py
Phase-5 — Security Rule Engine loader

Loads YAML/JSON security rule definitions and provides a query interface.
Rules are evaluated at runtime against request context to enforce policies.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SecurityRule:
    rule_id: str
    name: str
    category: str
    severity: str
    enabled: bool = True
    conditions: Dict[str, Any] = field(default_factory=dict)
    actions: List[str] = field(default_factory=list)
    description: str = ""


class SecurityRulesLoader:
    """Loads and caches security rules from files or env."""

    def __init__(self, rules_path: Optional[str] = None) -> None:
        self._path = rules_path or os.getenv("SECURITY_RULES_PATH", "config/security_rules.json")
        self._rules: Dict[str, SecurityRule] = {}
        self._log = logging.getLogger(self.__class__.__name__)

    def load(self) -> int:
        """Load rules from the configured path. Returns count loaded."""
        path = Path(self._path)
        if not path.exists():
            self._log.warning("Security rules file not found: %s", path)
            return 0
        try:
            with open(path) as fh:
                data = json.load(fh)
            rules_data = data if isinstance(data, list) else data.get("rules", [])
            for item in rules_data:
                rule = SecurityRule(
                    rule_id=item["rule_id"],
                    name=item.get("name", item["rule_id"]),
                    category=item.get("category", "general"),
                    severity=item.get("severity", "medium"),
                    enabled=item.get("enabled", True),
                    conditions=item.get("conditions", {}),
                    actions=item.get("actions", []),
                    description=item.get("description", ""),
                )
                self._rules[rule.rule_id] = rule
            self._log.info("Loaded %d security rules from %s", len(self._rules), path)
            return len(self._rules)
        except Exception as exc:
            self._log.error("Failed to load security rules: %s", exc)
            return 0

    def get_rule(self, rule_id: str) -> Optional[SecurityRule]:
        return self._rules.get(rule_id)

    def list_rules(self, category: Optional[str] = None, enabled_only: bool = True) -> List[SecurityRule]:
        rules = list(self._rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        if category:
            rules = [r for r in rules if r.category == category]
        return rules

    def evaluate(self, context: Dict[str, Any]) -> List[SecurityRule]:
        """Return rules whose conditions match the given context."""
        matched = []
        for rule in self.list_rules():
            if self._matches(rule, context):
                matched.append(rule)
        return matched

    def _matches(self, rule: SecurityRule, context: Dict[str, Any]) -> bool:
        for key, expected in rule.conditions.items():
            actual = context.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    @property
    def rule_count(self) -> int:
        return len(self._rules)


_loader: Optional[SecurityRulesLoader] = None


def get_security_rules_loader() -> SecurityRulesLoader:
    global _loader
    if _loader is None:
        _loader = SecurityRulesLoader()
        _loader.load()
    return _loader
