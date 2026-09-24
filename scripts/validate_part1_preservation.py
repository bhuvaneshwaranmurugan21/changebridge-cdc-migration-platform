#!/usr/bin/env python3
"""Verify immutable Part 1 evidence digests in the current ChangeBridge tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path("evidence/part1/stage5/protected-baseline.json")


def validate(root: Path) -> dict[str, object]:
    baseline = json.loads((root / BASELINE).read_text(encoding="utf-8"))
    artifacts = baseline.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 8:
        raise ValueError("CB21P001_PROTECTED_SET_MISMATCH")
    checked = []
    for row in artifacts:
        relative = row.get("path")
        expected = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("CB21P002_INVALID_PROTECTED_RECORD")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"CB21P003_PROTECTED_ARTIFACT_MISSING: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"CB21P004_PROTECTED_ARTIFACT_DRIFT: {relative}")
        checked.append(relative)
    return {"checked": checked, "count": len(checked), "result": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.root.resolve()), sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
