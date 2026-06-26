#!/usr/bin/env python3
"""verify_release.py — Phase 14: Artifact Integrity Verification
Customer runs this to verify their downloaded ZIP is authentic.

Usage:
  python verify_release.py MT5TradingEA_v3.20_production_20260626.zip
  python verify_release.py --server-key <key> MT5TradingEA_v3.20_*.zip
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

SOURCE_EXTENSIONS = {".mq5", ".mqh", ".py", ".ts", ".tsx", ".js", ".jsx",
                     ".sql", ".sh", ".env", ".pem", ".key", ".cert"}


@dataclass
class VerifyResult:
    ok: bool
    errors: list
    warnings: list
    manifest: dict


def verify_zip(zip_path: Path, server_public_key: str = "") -> VerifyResult:
    errors, warnings = [], []

    if not zip_path.exists():
        return VerifyResult(False, [f"File not found: {zip_path}"], [], {})

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        # Check 1: No source files
        for name in names:
            p = Path(name)
            ext = p.suffix.lower()
            basename = p.name.lower()
            if ext in SOURCE_EXTENSIONS:
                errors.append(f"SOURCE LEAK DETECTED: {name}")
            elif basename.startswith(".env"):
                errors.append(f"SOURCE LEAK DETECTED: {name} (env file)")

        # Check 2: Required files
        required = {"manifest.json", "CHECKSUMS.txt", "README_INSTALL.txt"}
        for m in required - set(names):
            errors.append(f"Missing required file: {m}")

        if errors:
            return VerifyResult(False, errors, warnings, {})

        # Check 3: Read manifest
        manifest = json.loads(zf.read("manifest.json").decode())

        # Check 4: Verify checksums
        checksums_raw = zf.read("CHECKSUMS.txt").decode()
        checksum_map = {}
        for line in checksums_raw.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("  ", 1)
            if len(parts) == 2:
                checksum_map[parts[1].strip()] = parts[0].strip()

        for name in names:
            if name in checksum_map:
                actual = hashlib.sha256(zf.read(name)).hexdigest()
                if not hmac.compare_digest(actual, checksum_map[name]):
                    errors.append(f"CHECKSUM MISMATCH: {name}")

        # Check 5: .ex5 SHA matches manifest
        ex5_files = [n for n in names if n.endswith(".ex5")]
        for ex5 in ex5_files:
            actual_sha = hashlib.sha256(zf.read(ex5)).hexdigest()
            manifest_sha = manifest.get("ea_binary_sha256", "")
            if manifest_sha and not hmac.compare_digest(actual_sha, manifest_sha):
                errors.append(f"EA binary SHA mismatch: {ex5}")

        # Check 6: Manifest signature
        if server_public_key:
            sig = manifest.pop("signature", "")
            canonical = json.dumps(
                {k: v for k, v in manifest.items() if k != "signature"},
                sort_keys=True, separators=(",", ":")
            )
            expected_sig = hmac.new(
                server_public_key.encode(), canonical.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                errors.append("Manifest signature INVALID — file may be tampered")
            manifest["signature"] = sig

        if not ex5_files:
            warnings.append("No .ex5 file found in ZIP")

    return VerifyResult(len(errors) == 0, errors, warnings, manifest)


def main():
    p = argparse.ArgumentParser(description="Verify MT5 EA release artifact")
    p.add_argument("zip_path", type=Path)
    p.add_argument("--server-key", default="")
    args = p.parse_args()

    print(f"Verifying: {args.zip_path}")
    result = verify_zip(args.zip_path, args.server_key)

    for w in result.warnings:
        print(f"WARNING: {w}")

    if result.ok:
        m = result.manifest
        print(f"VERIFIED: Version={m.get('version')} Built={m.get('build_time_utc')}")
    else:
        print("FAILED:")
        for e in result.errors:
            print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
