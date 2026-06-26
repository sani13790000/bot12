"""
PHASE 17 — deploy_validator.py
CI gate: validates Dockerfile, docker-compose, env vars before deploy.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ValidationResult:
    passed: bool
    message: str = ""
    details: List[str] = field(default_factory=list)


class DeploymentValidator:
    REQUIRED_ENV_KEYS = ["JWT_SECRET_KEY", "SUPABASE_URL", "SUPABASE_KEY", "REDIS_URL", "ENVIRONMENT"]

    def lint_dockerfile(self, content: str) -> ValidationResult:
        issues = []
        for f in re.findall(r"^FROM\s+(\S+)", content, re.M):
            if ":latest" in f:
                issues.append(f"Base image not pinned (uses :latest): {f}")
        non_root = [u for u in re.findall(r"^USER\s+(\S+)", content, re.M) if u not in ("root", "0")]
        if not non_root:
            issues.append("No non-root USER instruction found - running as root is insecure")
        if "HEALTHCHECK" not in content:
            issues.append("HEALTHCHECK instruction missing")
        if issues:
            return ValidationResult(passed=False, message="; ".join(issues), details=issues)
        return ValidationResult(passed=True, message="Dockerfile OK")

    def lint_compose(self, content: str) -> ValidationResult:
        issues = []
        if re.findall(r"requirepass\s+(?!\$\{)([^\s\n]+)", content):
            issues.append("Hardcoded Redis password detected")
        if re.findall(r'"0\.0\.0\.0:\d+:\d+"', content):
            issues.append("Wildcard port binding (0.0.0.0) detected")
        if issues:
            return ValidationResult(passed=False, message="; ".join(issues), details=issues)
        return ValidationResult(passed=True, message="compose OK")

    def validate_env(self, env: Dict[str, str]) -> ValidationResult:
        issues = []
        for key in self.REQUIRED_ENV_KEYS:
            if key not in env or not env[key]:
                issues.append(f"Missing required env var: {key}")
        jwt = env.get("JWT_SECRET_KEY", "")
        if jwt and len(jwt) < 32:
            issues.append(f"JWT_SECRET_KEY too short ({len(jwt)} chars)")
        if env.get("ENVIRONMENT") == "production" and env.get("ALLOWED_ORIGINS", "").strip() in ("*", '["*"]', ""):
            issues.append("Wildcard ALLOWED_ORIGINS not permitted in production")
        if issues:
            return ValidationResult(passed=False, message="; ".join(issues), details=issues)
        return ValidationResult(passed=True, message="env OK")

    def full_report(self, dockerfile_content: str, compose_content: str, env: Dict[str, str]) -> Dict[str, Any]:
        checks = []
        for name, result in [("dockerfile", self.lint_dockerfile(dockerfile_content)), ("compose", self.lint_compose(compose_content)), ("env", self.validate_env(env))]:
            checks.append({"check": name, "passed": result.passed, "message": result.message})
        return {"passed": all(c["passed"] for c in checks), "checks": checks, "summary": f"{sum(c['passed'] for c in checks)}/{len(checks)} checks passed"}
