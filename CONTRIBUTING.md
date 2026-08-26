# Contributing

**English** · [فارسی](CONTRIBUTING.fa.md)

Thanks for helping improve AI Workspace. Please keep changes reviewable, secret-free, and aligned with phase-1 architecture (Bridge ↔ Worker ↔ LM Studio).

## Ground rules

- Do **not** commit `.env`, keys, cookies, or real credentials.
- Prefer English for code, comments, commit messages, and default docs; add/update Persian mirrors under `docs/fa/` and `*.fa.md` when changing user-facing documentation.
- Do not revive legacy paths (`archive/legacy/`, root HTML key injection, desktop GUI) as the product UI.
- Keep Bridge port documentation accurate (**8010** host default).

## Development setup

Follow [docs/setup.md](docs/setup.md) and the Quick start in [readme.md](readme.md).

## Quality gate

Before opening a PR:

```powershell
powershell -File scripts/qa.ps1
```

Or manually: ruff, black, isort, flake8, mypy, pytest under `backend/`.

## Pull requests

1. Branch from `main` with a focused scope.
2. Describe *why* and how to test.
3. Update docs (EN + FA) when behavior or ops steps change.
4. Link related issues if any.

## Security reports

Do not open public issues for exploitable vulnerabilities. Follow [SECURITY.md](SECURITY.md).

## License

By contributing, you agree your work is licensed under the [MIT License](LICENSE).
