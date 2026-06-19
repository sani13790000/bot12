#!/usr/bin/env python3
"""Galaxy Vast AI - Pre-flight startup validator
Run this before docker compose up to catch all config errors early.
Usage: python3 startup_check.py
"""
from __future__ import annotations

import os
import sys
import importlib
from pathlib import Path

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0
warnings = 0


def ok(msg: str) -> None:
    global passed
    passed += 1
    print(f"{GREEN}  ✅ {msg}{RESET}")


def fail(msg: str, hint: str = "") -> None:
    global failed
    failed += 1
    print(f"{RED}  ❌ {msg}{RESET}")
    if hint:
        print(f"{YELLOW}     → {hint}{RESET}")


def warn(msg: str) -> None:
    global warnings
    warnings += 1
    print(f"{YELLOW}  ⚠️  {msg}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{BLUE}── {title} " + "─" * (50 - len(title)) + f"{RESET}")


print(f"{BOLD}\nGalaxy Vast AI Trading Platform — Pre-flight Check{RESET}")
print("=" * 60)

# 1. Python version
section("Python Version")
if sys.version_info >= (3, 11):
    ok(f"Python {sys.version.split()[0]}")
else:
    fail(f"Python {sys.version.split()[0]} — requires 3.11+",
         "Install Python 3.11: https://python.org")

# 2. .env file
section(".env File")
env_path = Path(".env")
if env_path.exists():
    ok(".env file found")
else:
    fail(".env not found",
         "Run: cp .env.example .env  then fill in the values")

# 3. Required env vars
section("Required Environment Variables")
REQUIRED_VARS = [
    ("SUPABASE_URL", "https://xxx.supabase.co"),
    ("SUPABASE_SERVICE_ROLE_KEY", "eyJ..."),
    ("JWT_SECRET_KEY", "min 64 hex chars"),
    ("LICENSE_SECRET", "min 32 chars hex"),
    ("LICENSE_SALT", "min 32 chars hex"),
]

if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv()

for var, hint in REQUIRED_VARS:
    val = os.getenv(var, "")
    if not val or val.startswith("REPLACE") or val.startswith("your") or val.startswith("generate"):
        fail(f"{var} not set", f"Expected: {hint}")
    elif var == "JWT_SECRET_KEY" and len(val) < 32:
        fail(f"{var} too short ({len(val)} chars)",
             "Run: python3 -c 'import secrets; print(secrets.token_hex(32))'")
    else:
        ok(f"{var} = {val[:12]}...")

# 4. Optional env vars
section("Optional Environment Variables")
OPTIONAL_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ADMIN_IDS",
    "MQL5_API_TOKEN",
    "SENTRY_DSN",
    "API_BASE_URL",
]
for var in OPTIONAL_VARS:
    val = os.getenv(var, "")
    if val:
        ok(f"{var} = {val[:15]}...")
    else:
        warn(f"{var} not set (optional)")

# 5. Python packages
section("Python Packages")
REQUIRED_PACKAGES = [
    "fastapi", "uvicorn", "pydantic", "pydantic_settings",
    "supabase", "redis",
    "xgboost", "sklearn", "numpy", "pandas",
    "jose", "cryptography",
    "prometheus_client",
]
OPTIONAL_PACKAGES = [
    ("stable_baselines3", "RL Agent (PPO)"),
    ("gymnasium", "RL Environment"),
    ("torch", "PyTorch for RL"),
    ("shap", "SHAP explainability"),
    ("pandas_ta", "Technical indicators"),
    ("sentry_sdk", "Error tracking"),
]
for pkg in REQUIRED_PACKAGES:
    mod = pkg.replace("-", "_")
    try:
        importlib.import_module(mod)
        ok(pkg)
    except ImportError:
        try:
            importlib.import_module(pkg)
            ok(pkg)
        except ImportError:
            fail(f"{pkg} not installed", f"pip install {pkg}")

for pkg, desc in OPTIONAL_PACKAGES:
    try:
        importlib.import_module(pkg)
        ok(f"{pkg} ({desc})")
    except ImportError:
        warn(f"{pkg} not installed ({desc}) — pip install {pkg}")

# 6. Project structure
section("Project Structure")
CRITICAL_FILES = [
    "backend/api/main.py",
    "backend/core/config.py",
    "backend/core/logger.py",
    "backend/core/deps.py",
    "backend/core/retry.py",
    "backend/core/validators.py",
    "backend/agents/voting_engine.py",
    "backend/analysis/smc_engine.py",
    "backend/cache.py",
    "backend/middleware/observability.py",
    "dashboard/app.py",
    "Dockerfile",
    "Dockerfile.bot",
    "docker-compose.yml",
    ".env.example",
    "pyproject.toml",
    "ARCHITECTURE.md",
]
for f in CRITICAL_FILES:
    if Path(f).exists():
        ok(f)
    else:
        fail(f"{f} missing", "Run: git pull origin main")

# 7. Migrations
section("Database Migrations")
mig_dir = Path("supabase/migrations")
if mig_dir.exists():
    migs = sorted(mig_dir.glob("*.sql"))
    if len(migs) >= 13:
        ok(f"{len(migs)} migration files found")
    else:
        warn(f"Only {len(migs)} migration files. Expected 13+")
else:
    fail("supabase/migrations/ not found")

# ── Summary
print(f"\n{'=' * 60}")
print(f"{BOLD}Summary:{RESET}")
print(f"  {GREEN}✅ Passed  : {passed}{RESET}")
print(f"  {YELLOW}⚠️  Warnings: {warnings}{RESET}")
print(f"  {RED}❌ Failed  : {failed}{RESET}")
print(f"{'=' * 60}")

if failed == 0:
    print(f"\n{GREEN}{BOLD}🚀 All checks passed! You can now run:{RESET}")
    print("  docker compose up -d --build")
    print("")
    print("  Services:")
    print("  • API:       http://localhost:8000")
    print("  • API Docs:  http://localhost:8000/docs  (dev only)")
    print("  • Health:    http://localhost:8000/health")
    print("  • Dashboard: http://localhost:8501")
    print("  • Frontend:  http://localhost:3000")
else:
    print(f"\n{RED}{BOLD}❌ Fix the {failed} error(s) above before running docker compose.{RESET}")
    sys.exit(1)
