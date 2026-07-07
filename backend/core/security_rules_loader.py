"""
backend/core/security_rules_loader.py
Phase-5 Security Rules Loader

Loads and validates security rules from the database/config.
P5-SR-1: Rules are validated against a schema on load.
P5-SR-2: Invalid rules are rejected with a clear error message.
P5-SR-3: Rules are cached in-memory with a TTL.
P5-SR-4: Hot-reload triggered by DB notification or config change.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 300.0  # 5 minutes


@dataclass
class SecurityRule:
    """A single security rule definition."""

    rule_id: str
    name: str
    rule_type: str  # "rate_limit" | "ip_block" | "pattern" | "threshold"
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)
    severity: str = "medium"  # "low" | "medium" | "high" | "critical"
    description: str = ""

    def validate(self) -> None:
        """Raise ValueError if rule is misconfigured."""
        if not self.rule_id:
            raise ValueError("SecurityRule.rule_id is required")
        if self.rule_type not in ("rate_limit", "ip_block", "pattern", "threshold"):
            raise ValueError(f"Unknown rule_type: {self.rule_type}")
        if self.severity not in ("low", "medium", "high", "critical"):
            raise ValueError(f"Unknown severity: {self.severity}")


class SecurityRulesLoader:
    """
    Loads, validates, and caches security rules.
    """

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._rules: List[SecurityRule] = []
        self._loaded_at: float = 0.0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def get_rules(
        self,
        rule_type: Optional[str] = None,
        force_reload: bool = False,
    ) -> List[SecurityRule]:
        """Return active security rules, using cache unless stale."""
        if force_reload or self._cache_stale():
            await self._load_from_db()
        rules = [r for r in self._rules if r.enabled]
        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        return rules

    async def reload(self) -> int:
        """Force a reload and return number of rules loaded."""
        await self._load_from_db()
        return len(self._rules)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _cache_stale(self) -> bool:
        return (time.monotonic() - self._loaded_at) > _CACHE_TTL

    async def _load_from_db(self) -> None:
        """Load rules from DB, validate, and update cache."""
        if self._db is None:
            logger.warning("[SecurityRulesLoader] no DB — using empty rule set")
            self._rules = []
            self._loaded_at = time.monotonic()
            return
        try:
            rows = await self._db.select("security_rules", {"enabled": True})
            rules = []
            for row in rows or []:
                try:
                    rule = SecurityRule(
                        rule_id=row["id"],
                        name=row.get("name", ""),
                        rule_type=row.get("rule_type", ""),
                        enabled=row.get("enabled", True),
                        params=row.get("params", {}),
                        severity=row.get("severity", "medium"),
                        description=row.get("description", ""),
                    )
                    rule.validate()  # P5-SR-2
                    rules.append(rule)
                except (ValueError, KeyError) as exc:
                    logger.error("[SecurityRulesLoader] invalid rule %s: %s", row.get("id"), exc)
            self._rules = rules
            self._loaded_at = time.monotonic()
            logger.info("[SecurityRulesLoader] loaded %d rules", len(rules))
        except Exception as exc:
            logger.error("[SecurityRulesLoader] DB load failed: %s", exc)


# Module-level singleton (DB injected at startup)
security_rules_loader = SecurityRulesLoader()
