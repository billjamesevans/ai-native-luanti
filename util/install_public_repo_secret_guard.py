#!/usr/bin/env python3
"""Install the local pre-push secret guard for this checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


HOOK = """#!/bin/sh
set -eu

repo_root=$(git rev-parse --show-toplevel)
scanner="$repo_root/util/scan_public_repo_secrets.py"

python3 "$scanner" --tracked --untracked
python3 "$scanner" --pre-push
"""


def run_git(args: list[str]) -> str:
    completed = subprocess.run(["git", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def main() -> int:
    repo = Path(run_git(["rev-parse", "--show-toplevel"]).strip())
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-push"
    hook_path.write_text(HOOK)
    os.chmod(hook_path, 0o755)
    print(f"Installed local pre-push secret guard at {hook_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
