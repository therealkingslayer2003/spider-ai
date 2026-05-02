# Development Scripts

## Formatting & Linting

Use `ruff` for all code quality checks:

```bash
# Format code
uv run ruff format app/ tests/

# Check formatting without changes
uv run ruff format --check app/ tests/

# Lint and auto-fix issues
uv run ruff check --fix app/ tests/
```

## Automatic formatting before push

### Setup (one-time)

Install git hooks so code is checked before every push:

**Windows:**
```powershell
python scripts/setup-hooks.py
```

**macOS/Linux:**
```bash
python scripts/setup-hooks.py
```

### What happens

- Before you push, the `pre-push` hook runs `uv run ruff format --check app/ tests/`
- If formatting issues are found, the push is **blocked**
- Fix by running `uv run ruff format app/ tests/`, then commit and push again
- To bypass (not recommended): `git push --no-verify`

### Manual hook setup (if `setup-hooks.py` doesn't work)

**Windows (PowerShell):**
```powershell
Copy-Item scripts/pre-push.ps1 .git/hooks/pre-push
# Then configure Git to use PowerShell:
git config core.hooksPath scripts
```

**macOS/Linux (bash):**
```bash
cp scripts/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

## Files

- `pre-push` — Unix/Linux/macOS git hook
- `pre-push.ps1` — Windows PowerShell git hook
- `setup-hooks.py` — Automated hook installer
