#!/usr/bin/env python3
"""Build the deterministic complete Stage 3 handoff fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from changebridge.normalizer import write_bundle_atomic
from changebridge.snapshot_handoff import build_full_handoff, normalize_full_handoff

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "tests/fixtures/part2-stage3/handoff"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing fixture: {args.output}")
    manifest = build_full_handoff(ROOT, args.output)
    bundle = normalize_full_handoff(ROOT, args.output)
    write_bundle_atomic(args.output / "normalized", bundle)
    result = {
        "result": "PASS",
        "manifest_id": manifest["manifest_id"],
        "accepted": bundle.report["accepted_count"],
        "quarantined": bundle.report["quarantined_count"],
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
