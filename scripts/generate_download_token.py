#!/usr/bin/env python3
"""generate_download_token.py — Phase 14: Signed Time-Limited Download Tokens

Usage:
  python scripts/generate_download_token.py \
      --version 3.20 \
      --zip releases/MT5TradingEA_v3.20_production_20260626.zip \
      --customer-id cust_abc123 \
      --ttl 86400

  python scripts/generate_download_token.py --verify <token>
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

BUILD_SECRET = os.environ.get("BUILD_SECRET", "dev-secret-change-in-production")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_token(
    version: str,
    zip_sha256: str,
    customer_id: str,
    ttl_seconds: int = 86400,
    max_downloads: int = 3,
    secret: str = BUILD_SECRET,
) -> str:
    """Generate signed download token."""
    payload = {
        "version":       version,
        "zip_sha256":    zip_sha256,
        "customer_id":   customer_id,
        "exp":           int(time.time()) + ttl_seconds,
        "max_downloads": max_downloads,
        "issued_at":     int(time.time()),
        "nonce":         os.urandom(8).hex(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sig = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    payload["sig"] = sig
    raw = json.dumps(payload, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def verify_token(token: str, secret: str = BUILD_SECRET) -> dict:
    """Verify and decode a download token."""
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except Exception as e:
        raise ValueError(f"Token decode failed: {e}")

    sig = payload.pop("sig", "")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected):
        raise ValueError("Token signature invalid — possible tampering")

    if time.time() > payload["exp"]:
        exp_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(payload["exp"]))
        raise ValueError(f"Token expired at {exp_str}")

    payload["sig"] = sig
    payload["valid"] = True
    return payload


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--verify")
    p.add_argument("--version")
    p.add_argument("--zip", type=Path)
    p.add_argument("--customer-id", default="unknown")
    p.add_argument("--ttl", type=int, default=86400)
    p.add_argument("--max-downloads", type=int, default=3)
    args = p.parse_args()

    if args.verify:
        try:
            payload = verify_token(args.verify)
            print("Token VALID:", json.dumps(payload, indent=2))
        except ValueError as e:
            print(f"INVALID: {e}")
            sys.exit(1)
        return

    if not args.version or not args.zip:
        p.error("--version and --zip required")

    if not args.zip.exists():
        print(f"ZIP not found: {args.zip}")
        sys.exit(1)

    zip_sha = sha256_file(args.zip)
    token = generate_token(
        args.version, zip_sha, args.customer_id, args.ttl, args.max_downloads,
    )
    exp = int(time.time()) + args.ttl
    exp_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(exp))
    print(f"Token: {token}")
    print(f"Expires: {exp_str}")
    print(f"Customer: {args.customer_id}")


if __name__ == "__main__":
    main()
