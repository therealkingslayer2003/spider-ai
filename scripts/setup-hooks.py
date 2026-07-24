#!/usr/bin/env python3
"""
Setup script to install git hooks for automated code formatting before push.
Usage:
  python scripts/setup-hooks.py
"""

import os
import shutil
import sys
from pathlib import Path


def setup_hooks():
    """Install git hooks for code formatting."""
    repo_root = Path(__file__).parent.parent
    hooks_dir = repo_root / ".git" / "hooks"

    if not hooks_dir.exists():
        print("❌ Error: .git/hooks directory not found. Are you in a git repository?")
        sys.exit(1)

    # Detect OS
    is_windows = sys.platform == "win32"

    hook_name = "pre-push"
    source = repo_root / "scripts" / "pre-push"
    dest = hooks_dir / hook_name

    if not source.exists():
        print(f"❌ Error: {source} not found.")
        sys.exit(1)

    shutil.copy(source, dest)

    # Make executable on Unix
    if not is_windows:
        os.chmod(dest, 0o755)

    print(f"✅ Installed pre-push hook at {dest}")
    print("\n✨ Git will automatically run this hook before each push.")

    print("\n🎉 Git hooks installed successfully!")
    print("\nWhat happens now:")
    print("  - Before you 'git push', the hook will run 'python format.py --check'")
    print("  - If formatting issues are found, the push is blocked")
    print("  - Fix with: python format.py")
    print("  - Then commit and push again")
    print("\nTo bypass (not recommended): git push --no-verify")


if __name__ == "__main__":
    setup_hooks()
