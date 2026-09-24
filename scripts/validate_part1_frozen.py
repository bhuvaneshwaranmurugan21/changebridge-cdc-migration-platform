#!/usr/bin/env python3
"""Execute the complete historical Part 1 gate on its immutable merged tree."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PART1_COMMIT = "6ae4e071782bddeb5a35f9635262e868f52df6f5"
PART1_TREE = "2126b55cb85844189aa9907452de22847ca43e98"


def run(root: Path) -> dict[str, object]:
    actual_tree = subprocess.check_output(
        ["git", "rev-parse", f"{PART1_COMMIT}^{{tree}}"], cwd=root, text=True
    ).strip()
    if actual_tree != PART1_TREE:
        raise RuntimeError(f"CB21V001_PART1_TREE_MISMATCH:{actual_tree}")
    temporary_parent = Path(tempfile.mkdtemp(prefix="changebridge-part1-frozen."))
    worktree = temporary_parent / "tree"
    added = False
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), PART1_COMMIT],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        added = True
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((str(worktree / "src"), str(worktree)))
        subprocess.run(
            [sys.executable, "scripts/validate_part1_closure.py"],
            cwd=worktree,
            check=True,
            env=environment,
        )
        subprocess.run(
            [sys.executable, "-m", "pytest"],
            cwd=worktree,
            check=True,
            env=environment,
        )
        return {
            "commit": PART1_COMMIT,
            "historical_tests": "PASS",
            "historical_validator": "PASS",
            "result": "PASS",
            "tree": PART1_TREE,
        }
    finally:
        if added:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
        temporary_parent.rmdir()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(run(root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
