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

**Windows (batch):**
```powershell
python scripts/setup-hooks.py
```

**macOS/Linux (bash):**
```bash
python scripts/setup-hooks.py
```

### What happens

- Before you push, the `pre-push` hook automatically runs `uv run ruff format --check app/ tests/`
- If formatting issues are found, the push is **blocked**
- Fix by running `uv run ruff format app/ tests/`, then commit and push again
- To bypass (not recommended): `git push --no-verify`

### Manual hook setup (if `setup-hooks.py` doesn't work)

**Windows (PowerShell):**
```powershell
Copy-Item scripts/pre-push .git/hooks/pre-push
```

**macOS/Linux:**
```bash
cp scripts/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

> **Note:** Git for Windows uses its own `sh.exe` to run hooks, so the same shell script works on all platforms.

## Files

- `pre-push` — Git hook (works on Windows, macOS, and Linux)
- `setup-hooks.py` — Automated hook installer
