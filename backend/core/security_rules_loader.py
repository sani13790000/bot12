"""
backend/core/security_rules_loader.py
Phase-5 — Security Rule Engine loader

Reads backend/core/security_rules.yaml and exposes typed rule objects.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

LOGGER = logging.getLogger(__name__)

DEFAULT_RULES_PATH = Path(__file__).with_name("security_rules.yaml")


@dataclass
class SecurityRule:
    """Single security rule definition."""

    id: str
    name: str
    severity: str
    condition: str
    action: str
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class SecurityRulesLoader:
    """Loads and caches security rules from YAML."""

    def __init__(self, path: Optional[os.PathLike] = None) -> None:
        self.path = Path(path) if path else DEFAULT_RULES_PATH
        self._rules: List[SecurityRule] = []
        self._loaded = False

    def load(self) -> List[SecurityRule]:
        if self._loaded:
            return self._rules

        if not self.path.exists():
            LOGGER.warning("Security rules file not found: %s", self.path)
            self._loaded = True
            return self._rules

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            LOGGER.error("Failed to parse security rules: %s", exc)
            self._loaded = True
            return self._rules

        for raw in data.get("rules", []):
            try:
                self._rules.append(
                    SecurityRule(
                        id=raw["id"],
                        name=raw.get("name", raw["id"]),
                        severity=raw.get("severity", "MEDIUM"),
                        condition=raw["condition"],
                        action=raw["action"],
                        enabled=raw.get("enabled", True),
                        metadata=raw.get("metadata", {}),
                    )
                )
            except KeyError as exc:
                LOGGER.warning("Skipping invalid security rule: missing %s", exc)

        self._loaded = True
        LOGGER.info("Loaded %d security rules", len(self._rules))
        return self._rules

    def get_enabled_rules(self) -> List[SecurityRule]:
        return [r for r in self.load() if r.enabled]


# Module-level singleton
_rules_loader = SecurityRulesLoader()


def get_security_rules() -> List[SecurityRule]:
    return _rules_loader.get_enabled_rules()
