"""
backend/core/security_rules_loader.py
Galaxy Vast AI — Security Rules Loader
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


class SecurityRulesLoader:
    """Load and manage security rules from config."""

    def __init__(self, rules_path: Optional[str] = None) -> None:
        self._rules_path = rules_path or os.environ.get('SECURITY_RULES_PATH', '')
        self._rules: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> Dict[str, Any]:
        if self._rules_path and Path(self._rules_path).exists():
            try:
                with open(self._rules_path, 'r') as f:
                    self._rules = json.load(f)
                self._loaded = True
            except Exception as e:
                _LOG.error('Failed to load security rules: %s', e)
        else:
            self._rules = self._default_rules()
            self._loaded = True
        return self._rules

    def _default_rules(self) -> Dict[str, Any]:
        return {
            'max_login_attempts': 5,
            'lockout_duration_seconds': 300,
            'password_min_length': 12,
            'session_timeout_seconds': 3600,
            'require_2fa': False,
        }

    def get(self, key: str, default: Any = None) -> Any:
        if not self._loaded:
            self.load()
        return self._rules.get(key, default)

    @property
    def rules(self) -> Dict[str, Any]:
        if not self._loaded:
            self.load()
        return self._rules


_loader: Optional[SecurityRulesLoader] = None


def get_security_rules() -> SecurityRulesLoader:
    global _loader
    if _loader is None:
        _loader = SecurityRulesLoader()
        _loader.load()
    return _loader
