build_release.py Phase 7

Release artifact strategy:
1. compile .mq5 → .ex5 (MetaEditor64.exe)
2. Build signed manifest (HMAC-SHA256)
3. Package: ex5 + README + manifest (NO .mq5/.mqh)
4. Verify: no source files in ZIP
5. Archive source (internal only)

Customer دریافت می‌کند: فقط .ex5 + README
Source files هرگز در release نیستند