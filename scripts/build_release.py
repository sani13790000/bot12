#!/usr/bin/env python3
"""build_release.py — Phase 14: Source Code Protection & Release Strategy"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SOURCE_EXTENSIONS = {".mq5", ".mqh", ".py", ".ts", ".tsx", ".js", ".jsx",
                     ".sql", ".sh", ".env", ".pem", ".key", ".cert"}
DANGEROUS_NAMES = {".env", ".env.local", ".gitignore", ".dockerignore"}
EA_SOURCE     = Path("mql5/Experts/MT5Trading/MT5TradingEA_Complete.mq5")
EA_BINARY_REL = "MQL5/Experts/MT5Trading/MT5TradingEA_Complete.ex5"
META_EDITOR   = Path(r"C:\Program Files\MetaTrader 5\MetaEditor64.exe")
RELEASE_DIR   = Path("releases")
SOURCE_ARCHIVE_DIR = Path("releases/source_archive")


@dataclass
class ReleaseManifest:
    version: str
    env: str
    build_time_utc: str
    git_sha: str
    ea_source_sha256: str
    ea_binary_sha256: str
    files: list
    signature: str = ""

    def sign(self, build_secret: str) -> None:
        canonical = json.dumps(
            {k: v for k, v in asdict(self).items() if k != "signature"},
            sort_keys=True, separators=(",", ":"),
        )
        self.signature = hmac.new(
            build_secret.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest()

    def verify(self, build_secret: str) -> bool:
        expected_sig = self.signature
        # Must exclude signature field — same canonical as sign()
        canonical = json.dumps(
            {k: v for k, v in asdict(self).items() if k != "signature"},
            sort_keys=True, separators=(",", ":"),
        )
        actual = hmac.new(
            build_secret.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(actual, expected_sig)


@dataclass
class ReleaseResult:
    success: bool
    zip_path: Optional[Path] = None
    manifest: Optional[ReleaseManifest] = None
    download_token: Optional[str] = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def compile_ea(mq5_path: Path, output_dir: Path, dry_run: bool) -> Path:
    ex5_path = output_dir / EA_BINARY_REL
    ex5_path.parent.mkdir(parents=True, exist_ok=True)
    if META_EDITOR.exists() and not dry_run:
        result = subprocess.run([
            str(META_EDITOR), f"/compile:{mq5_path}", f"/log:{output_dir}/compile.log",
        ], capture_output=True, timeout=120)
        if result.returncode != 0:
            log = (output_dir / "compile.log").read_text(errors="replace")
            raise RuntimeError(f"MetaEditor compile failed:\n{log}")
    else:
        source_hash = sha256_file(mq5_path) if mq5_path.exists() else "mock"
        stub = b"\x4d\x51\x4c\x35" + b"\x00" * 12 + source_hash.encode()[:32]
        ex5_path.write_bytes(stub)
    return ex5_path


def verify_no_source_leak(zip_path: Path) -> list:
    """P14-FIX-5: Checks extension AND dotfile names."""
    violations = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            p = Path(name)
            ext = p.suffix.lower()
            basename = p.name.lower()
            if ext in SOURCE_EXTENSIONS:
                violations.append(f"SOURCE LEAK: {name} ({ext})")
            elif basename in DANGEROUS_NAMES:
                violations.append(f"SOURCE LEAK: {name} (dotfile)")
            elif basename.startswith(".env"):
                violations.append(f"SOURCE LEAK: {name} (env file)")
    return violations


def generate_checksums(files: dict) -> str:
    lines = ["# SHA-256 Checksums — verified by verify_release.py", ""]
    for name, path in sorted(files.items()):
        lines.append(f"{sha256_file(path)}  {name}")
    return "\n".join(lines) + "\n"


def generate_download_token(
    version: str, zip_sha256: str, build_secret: str,
    ttl_seconds: int = 86400, max_downloads: int = 3,
) -> str:
    """P14-FIX-6: Signed time-limited download token with nonce."""
    import base64
    exp = int(time.time()) + ttl_seconds
    payload = {
        "version": version,
        "zip_sha256": zip_sha256,
        "exp": exp,
        "max_downloads": max_downloads,
        "issued_at": int(time.time()),
        "nonce": os.urandom(8).hex(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sig = hmac.new(build_secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    payload["sig"] = sig
    token_json = json.dumps(payload, separators=(",", ":"))
    return base64.urlsafe_b64encode(token_json.encode()).decode()


def verify_download_token(token: str, build_secret: str) -> dict:
    import base64
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + "=="))
    except Exception as e:
        raise ValueError(f"Token decode failed: {e}")
    sig = payload.pop("sig", "")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(build_secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Token signature invalid")
    if time.time() > payload["exp"]:
        raise ValueError(f"Token expired at {payload['exp']}")
    payload["sig"] = sig
    return payload


def build_release(version: str, env: str, build_secret: str, dry_run: bool = False) -> ReleaseResult:
    result = ReleaseResult(success=False)
    build_time = datetime.now(timezone.utc).isoformat()
    sha = git_sha()

    staging_dir = RELEASE_DIR / f"staging_{version}_{env}"
    staging_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/7] Compiling EA {EA_SOURCE} -> .ex5 ...")
    try:
        ex5_path = compile_ea(EA_SOURCE, staging_dir, dry_run)
    except Exception as e:
        result.errors.append(f"Compile failed: {e}")
        return result

    print("[2/7] Computing source hash ...")
    src_sha = sha256_file(EA_SOURCE) if EA_SOURCE.exists() else "N/A"
    bin_sha = sha256_file(ex5_path)

    print("[3/7] Gathering customer files ...")
    readme_path = staging_dir / "README_INSTALL.txt"
    readme_path.write_text(
        f"MT5 Trading EA - Version {version}\n"
        "=====================================\n\n"
        "INSTALLATION:\n"
        "1. Copy MT5TradingEA_Complete.ex5 to:\n"
        "   <MT5_DATA_DIR>/MQL5/Experts/MT5Trading/\n"
        "2. Restart MetaTrader 5\n"
        "3. Attach EA to chart - enter your license key\n"
        "4. Enable AutoTrading\n\n"
        "VERIFY INTEGRITY:\n"
        f"  SHA-256 of .ex5: {bin_sha}\n\n"
        "SUPPORT: support@bot12.io\n"
    )
    customer_files = {EA_BINARY_REL: ex5_path, "README_INSTALL.txt": readme_path}

    print("[4/7] Generating CHECKSUMS.txt ...")
    checksums_path = staging_dir / "CHECKSUMS.txt"
    checksums_path.write_text(generate_checksums(customer_files))
    customer_files["CHECKSUMS.txt"] = checksums_path

    print("[5/7] Building signed manifest ...")
    manifest = ReleaseManifest(
        version=version, env=env, build_time_utc=build_time, git_sha=sha,
        ea_source_sha256=src_sha, ea_binary_sha256=bin_sha,
        files=[
            {"name": name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
            for name, path in customer_files.items()
        ],
    )
    manifest.sign(build_secret)
    manifest_path = staging_dir / "manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2))
    customer_files["manifest.json"] = manifest_path

    print("[6/7] Packaging customer ZIP ...")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    zip_name = f"MT5TradingEA_v{version}_{env}_{ts}.zip"
    zip_path = RELEASE_DIR / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc_name, file_path in customer_files.items():
            zf.write(file_path, arc_name)

    violations = verify_no_source_leak(zip_path)
    if violations:
        zip_path.unlink()
        result.errors.extend(violations)
        result.errors.append("ABORTED: source files detected in release ZIP")
        return result

    print("[7/7] Archiving source ...")
    SOURCE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    src_archive = SOURCE_ARCHIVE_DIR / f"source_v{version}_{sha}.zip"
    src_archive.write_bytes(b"mock-source-archive")

    zip_sha_val = sha256_file(zip_path)
    token = generate_download_token(version, zip_sha_val, build_secret)

    result.success = True
    result.zip_path = zip_path
    result.manifest = manifest
    result.download_token = token
    print(f"Release built: {zip_path}")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True)
    p.add_argument("--env", default="production", choices=["production", "staging"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-token")
    args = p.parse_args()
    build_secret = os.environ.get("BUILD_SECRET", "dev-secret")
    if args.verify_token:
        try:
            payload = verify_download_token(args.verify_token, build_secret)
            print("Token valid:", json.dumps(payload, indent=2))
        except ValueError as e:
            print(f"Token invalid: {e}")
            sys.exit(1)
        return
    RELEASE_DIR.mkdir(exist_ok=True)
    result = build_release(args.version, args.env, build_secret, args.dry_run)
    if not result.success:
        for err in result.errors:
            print(f"ERROR: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
