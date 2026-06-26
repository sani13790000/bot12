# Release Governance — MT5 Trading EA SaaS

## What Each Stakeholder Receives

### Customer (Subscriber)
| Artifact | Format | Contains |
|----------|--------|----------|
| EA Binary | `.ex5` | Compiled EA only — source not recoverable |
| Install Guide | `README_INSTALL.txt` | MT5 installation steps |
| Manifest | `manifest.json` | Version, SHA-256, build time, signature |
| Checksums | `CHECKSUMS.txt` | SHA-256 per file (GNU format) |

**Customer NEVER receives:**
- `.mq5` / `.mqh` source files
- Python backend source (`.py`)
- Frontend source (`.ts` / `.tsx`)
- Database schemas (`.sql`)
- Server secrets or credentials

---

### Admin / Internal Team
| Artifact | Location | Access |
|----------|----------|--------|
| `.mq5` source | `mql5/` (repo) | Dev team only |
| `.mqh` headers | `mql5/Include/` (repo) | Dev team only |
| Source archive | `releases/source_archive/` | Admin only |
| Build manifest | GitHub Actions artifact | Admin only |
| Download tokens | Generated per customer | Admin via `generate_download_token.py` |

---

## Release Pipeline

```
git tag v3.20
    │
    ▼
GitHub Actions: ea_release.yml
    │
    ├── Job 1: source-protection
    │   ├── Check Dockerfile has no .mq5 refs
    │   ├── Check .gitignore protects *.ex5, releases/
    │   └── Check .dockerignore excludes mql5/
    │
    ├── Job 2: build-ea
    │   ├── compile .mq5 → .ex5 (MetaEditor64 / CI mock)
    │   ├── generate CHECKSUMS.txt (SHA-256)
    │   ├── build manifest.json (HMAC-signed)
    │   ├── package ZIP (ex5 + README + manifest + checksums)
    │   ├── verify_release.py → abort if source detected
    │   └── upload artifact to GitHub Actions
    │
    ├── Job 3: github-release
    │   ├── final source-leak check
    │   ├── create GitHub Release with .zip asset
    │   └── generate release notes
    │
    └── Job 4: notify
        └── Telegram alert
```

---

## Download Token System

Tokens are **signed** (HMAC-SHA256) and **time-limited**.

### Generate (admin)
```bash
export BUILD_SECRET="<production-secret>"

python scripts/generate_download_token.py \
  --version 3.20 \
  --zip releases/MT5TradingEA_v3.20_production_20260626.zip \
  --customer-id cust_abc123 \
  --ttl 86400 \
  --max-downloads 3
```

### Token Contents
```json
{
  "version":       "3.20",
  "zip_sha256":    "abc123...",
  "customer_id":   "cust_abc123",
  "exp":           1782578935,
  "max_downloads": 3,
  "issued_at":     1782492535,
  "nonce":         "a1b2c3d4e5f6a7b8",
  "sig":           "hmac-sha256-hex..."
}
```

### Verify (customer)
```bash
python scripts/verify_release.py MT5TradingEA_v3.20_production_20260626.zip
```

---

## Artifact Table

| File | Customer | Admin | Notes |
|------|----------|-------|-------|
| `*.ex5` | ✅ | ✅ | Compiled binary only |
| `README_INSTALL.txt` | ✅ | ✅ | Installation guide |
| `manifest.json` | ✅ | ✅ | HMAC-signed |
| `CHECKSUMS.txt` | ✅ | ✅ | SHA-256 per file |
| `*.mq5` | ❌ | ✅ | Source — never ships |
| `*.mqh` | ❌ | ✅ | Headers — never ships |
| `*.py` | ❌ | ✅ | Backend — never ships |
| `source_archive/*.zip` | ❌ | ✅ | Internal archive |

---

## Security Guarantees

| Threat | Mitigation |
|--------|-----------|
| Source code theft | `.ex5` only in ZIP — `.mq5` never included |
| Tampered download | CHECKSUMS.txt + manifest.json signature |
| Replay download | Time-limited tokens with nonce |
| Unlimited downloads | `max_downloads` counter in token |
| MITM manifest swap | HMAC-SHA256(BUILD_SECRET) on manifest |
| Docker source leak | `.dockerignore` excludes `mql5/` |
| Git source push | `.gitignore` protects `releases/source_archive/` |

---

## .gitignore Required Entries
```gitignore
# Release artifacts
releases/
!releases/.gitkeep
*.ex5

# Source archive (internal)
releases/source_archive/
```

## .dockerignore Required Entries
```dockerignore
# MQL5 source
mql5/
*.mq5
*.mqh
*.ex5
```
