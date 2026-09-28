#!/usr/bin/env python3
"""Build the bounded Stage 4 apply fixture from the accepted Stage 3 handoff."""

from __future__ import annotations

import json
from pathlib import Path

from changebridge.transaction_assembler import build_apply_manifest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/part2-stage3/handoff/normalized/canonical.json"
TARGET = ROOT / "tests/fixtures/part2-stage4"
S = "0/194FB20"
TERMINAL = "0/194FE20"
SOURCE_HISTORY_DIGEST = "61b6a6af3a3befa54f80a17cbf65278bb35a72cbb70a59bf6c86cd0460a00634"
PREDECESSOR_MANIFEST = "cbefc7edceb284352970b9ef4f6726b88b694faff4e8678863d1245157cc6dc1"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(root: Path = ROOT) -> dict[str, object]:
    canonical = json.loads((root / SOURCE.relative_to(ROOT)).read_text(encoding="utf-8"))
    events = [event for event in canonical if event["operation"] != "snapshot"]
    if len(events) != 1 or events[0]["transaction_id"] != "tx-012-post-boundary":
        raise RuntimeError("CB24F001_UNEXPECTED_STAGE3_HANDOFF")
    generation_id = str(events[0]["generation_id"])
    manifest = build_apply_manifest(
        events,
        generation_id=generation_id,
        previous_frontier=S,
        terminal_frontier=TERMINAL,
        source_history_digest=SOURCE_HISTORY_DIGEST,
        predecessor_manifest_digest=PREDECESSOR_MANIFEST,
    )
    provenance = {
        "profile": "changebridge-stage24-fixture-provenance/1.0.0",
        "fixture_kind": "accepted-stage3-handoff-extraction",
        "synthetic": False,
        "source": "tests/fixtures/part2-stage3/handoff/normalized/canonical.json",
        "generation_id": generation_id,
        "snapshot_boundary": S,
        "terminal_frontier": TERMINAL,
        "event_count": len(events),
        "transaction_count": 1,
        "transaction_id": "tx-012-post-boundary",
        "manifest_id": manifest["manifest_id"],
    }
    target = root / TARGET.relative_to(ROOT)
    write(target / "canonical-events.json", events)
    write(target / "apply-manifest.json", manifest)
    write(target / "provenance.json", provenance)
    return provenance


if __name__ == "__main__":
    print(json.dumps(build(), sort_keys=True))
