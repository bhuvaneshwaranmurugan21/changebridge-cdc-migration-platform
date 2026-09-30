from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from changebridge.publication import PublicationError, publication_binding_manifest

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_acceptance_registry_is_exact_and_contiguous() -> None:
    registry = load("requirements/part2-stage7-acceptance.json")
    assert [row["id"] for row in registry["criteria"]] == [
        f"ST27-AC-{number:02d}" for number in range(1, 57)
    ]


def test_contract_catalog_resolves_json_schemas() -> None:
    catalog = load("contracts/stage27/catalog.json")
    for path in catalog["contracts"]:
        schema = load(path)
        jsonschema.Draft202012Validator.check_schema(schema)


def test_binding_rejects_execution_gate_with_failed_verdict() -> None:
    accepted = load("evidence/part2/stage6/proof-manifest.json")
    execution = copy.deepcopy(accepted)
    execution["gates"][0]["verdict"] = "FAIL"
    execution["gates"][0].pop("gate_digest")
    with pytest.raises(Exception, match="FAILED_GATE"):
        publication_binding_manifest(
            accepted_manifest=accepted,
            execution_manifest=execution,
            table_map={},
            accepted_reconciliation_digest="a" * 64,
            execution_reconciliation_digest="a" * 64,
        )


def test_binding_rejects_incomplete_physical_table_map() -> None:
    accepted = load("evidence/part2/stage6/proof-manifest.json")
    with pytest.raises(PublicationError, match="CB27B003_TABLE_MAP_INCOMPLETE"):
        publication_binding_manifest(
            accepted_manifest=accepted,
            execution_manifest=accepted,
            table_map={},
            accepted_reconciliation_digest="a" * 64,
            execution_reconciliation_digest="a" * 64,
        )
