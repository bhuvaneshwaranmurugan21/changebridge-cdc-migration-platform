#!/usr/bin/env python3
"""Execute the historical Part 2 Stage 3 gate on its immutable merged tree."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

STAGE3_COMMIT = "e9b4a6dc6d62c1c90a89ea4ba3c02ad6a0d6a601"
STAGE3_TREE = "775b6790edd7b671091e32b0e2787374e4bcb429"


def run(root: Path) -> dict[str, object]:
    actual_tree = subprocess.check_output(
        ["git", "rev-parse", f"{STAGE3_COMMIT}^{{tree}}"], cwd=root, text=True
    ).strip()
    if actual_tree != STAGE3_TREE:
        raise RuntimeError(f"CB24V001_STAGE3_TREE_MISMATCH:{actual_tree}")
    temporary_parent = Path(tempfile.mkdtemp(prefix="changebridge-stage23-frozen."))
    worktree = temporary_parent / "tree"
    added = False
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), STAGE3_COMMIT],
            cwd=root, check=True, capture_output=True, text=True,
        )
        added = True
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((str(worktree / "src"), str(worktree)))
        subprocess.run(
            [sys.executable, "scripts/validate_part2_stage3.py"],
            cwd=worktree, check=True, env=environment,
        )
        return {
            "commit": STAGE3_COMMIT,
            "historical_validator": "PASS",
            "protected_evidence": "PASS",
            "result": "PASS",
            "tree": STAGE3_TREE,
        }
    finally:
        if added:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=root, check=True, capture_output=True, text=True,
            )
        temporary_parent.rmdir()


if __name__ == "__main__":
    print(json.dumps(run(Path(__file__).resolve().parents[1]), sort_keys=True))
