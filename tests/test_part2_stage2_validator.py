from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "stage22_validator", ROOT / "scripts/validate_part2_stage2.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def load(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_acceptance_registry_is_exact_and_candidate_receipt_is_fail_closed() -> None:
    VALIDATOR.validate_acceptance(
        load("requirements/part2-stage2-acceptance.json"),
        load("evidence/part2/stage2/stage-receipt.json"),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda receipt: receipt["criteria"].pop(),
        lambda receipt: receipt["criteria"][0].__setitem__("id", "ST22-AC-99"),
        lambda receipt: receipt["criteria"][40].__setitem__("result", "PASS"),
        lambda receipt: receipt.__setitem__("criteria_passed", 41),
        lambda receipt: receipt.__setitem__("result", "PASS"),
    ],
)
def test_acceptance_mutations_are_rejected(mutation: Any) -> None:
    registry = load("requirements/part2-stage2-acceptance.json")
    receipt = copy.deepcopy(load("evidence/part2/stage2/stage-receipt.json"))
    mutation(receipt)
    with pytest.raises(VALIDATOR.Stage22Error):
        VALIDATOR.validate_acceptance(registry, receipt)


def test_reason_registry_matches_runtime_exactly() -> None:
    from changebridge.normalizer import REASON_CODES

    registry = load("contracts/normalization-reason-codes-v1.json")
    assert registry["closed"] is True
    assert set(registry["codes"]) == REASON_CODES


def test_full_stage_validator_passes() -> None:
    result = VALIDATOR.validate(ROOT)
    assert result["result"] == "PASS"
    assert result["criteria_passed"] == 40
    assert result["criteria_pending_external"] == 4
