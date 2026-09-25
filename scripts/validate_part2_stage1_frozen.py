#!/usr/bin/env python3
"""Execute the historical Part 2 Stage 1 gate on its immutable merged tree."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

STAGE1_COMMIT = "006a74119ebc4edc050e31ae171ca8d9fbe8b669"
STAGE1_TREE = "745f25fc394fd06c339ee22b432e3f8f26d5035d"


def run(root: Path) -> dict[str, object]:
    actual_tree = subprocess.check_output(
        ["git", "rev-parse", f"{STAGE1_COMMIT}^{{tree}}"], cwd=root, text=True
    ).strip()
    if actual_tree != STAGE1_TREE:
        raise RuntimeError(f"CB22V028_STAGE1_TREE_MISMATCH:{actual_tree}")
    temporary_parent = Path(tempfile.mkdtemp(prefix="changebridge-stage21-frozen."))
    worktree = temporary_parent / "tree"
    added = False
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), STAGE1_COMMIT],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        added = True
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((str(worktree / "src"), str(worktree)))
        subprocess.run(
            [sys.executable, "scripts/validate_part2_stage1.py"],
            cwd=worktree,
            check=True,
            env=environment,
        )
        return {
            "commit": STAGE1_COMMIT,
            "historical_validator": "PASS",
            "protected_evidence": "PASS",
            "result": "PASS",
            "tree": STAGE1_TREE,
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
    print(json.dumps(run(Path(__file__).resolve().parents[1]), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
