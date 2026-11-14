## What and why

## Checklist

- [ ] `ruff check src tests scripts` and `pytest` pass
- [ ] `python scripts/secrets_scan.py` passes (no keys, no personal ids, hosts or paths; test data is synthetic)
- [ ] New text is in both `locales/en.json` and `locales/th.json` (a test checks the keys match)
- [ ] I did not weaken a rule in SECURITY.md (approval-first, owner-only routes, denylist, secrets redaction). If I touched one, tests prove it still holds
- [ ] Docs updated (`docs/`, `CHANGELOG.md`)
