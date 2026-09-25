from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_part2_stage3 import Stage23Error, validate_acceptance

ROOT = Path(__file__).resolve().parents[1]


def _registry() -> dict[str, object]:
    return json.loads((ROOT / "requirements/part2-stage3-acceptance.json").read_text())


def _receipt() -> dict[str, object]:
    return {
        "criteria_total": 42,
        "criteria_passed": 38,
        "criteria_pending": 4,
        "result": "PENDING_EXTERNAL_CLOSURE",
        "criteria": [
            {
                "id": f"ST23-AC-{number:02d}",
                "result": "PASS" if number <= 38 else "PENDING",
                "evidence": ["proof"],
            }
            for number in range(1, 43)
        ],
    }


def test_acceptance_registry_and_candidate_receipt_agree() -> None:
    validate_acceptance(_registry(), _receipt())


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "premature", "counts"])
def test_acceptance_mutations_fail_closed(mutation: str) -> None:
    receipt = _receipt()
    rows = receipt["criteria"]
    assert isinstance(rows, list)
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = rows[-2]
    elif mutation == "premature":
        assert isinstance(rows[-1], dict)
        rows[-1]["result"] = "PASS"
    else:
        receipt["criteria_passed"] = 42
    with pytest.raises(Stage23Error):
        validate_acceptance(_registry(), receipt)
