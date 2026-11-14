# Contributing

Thanks for helping improve nano Agent. Small, focused changes are easiest to review.

## Before opening a change

- Read [SECURITY.md](SECURITY.md). Report vulnerabilities privately using the security advisory link in the repository.
- Keep examples synthetic. Never include credentials, tokens, personal identifiers, private chat data or machine-specific paths.
- Preserve approval before sending, owner-only API routes, tool input checks and the patch denylist.
- Add user-facing strings in both `src/nanoagent/locales/en.json` and `src/nanoagent/locales/th.json`.
- Update relevant docs and `CHANGELOG.md`.

## Local checks

Use Python 3.11 or newer:

```bash
python -m pip install -e ".[dev]"
ruff check src tests scripts
pytest
python scripts/secrets_scan.py
python scripts/secrets_scan.py --history
```

The CI workflow also builds and installs a wheel in a clean environment, checks the installer, scans the full Git history, and runs gitleaks.

## Pull requests

Describe the user-visible change, why it is needed, and how you checked it. Complete the checklist in the pull request template. Do not include live credentials or test against real LINE contacts; use synthetic fixtures and the fake provider.
