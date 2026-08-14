from changebridge.aws_evidence import validate_aws_lab_evidence
from changebridge.canonical import digest


def valid_bundle() -> dict[str, object]:
    payload: dict[str, object] = {
        "project": "changebridge-cdc-migration-platform",
        "claim_level": "AWS_LAB_VERIFIED",
        "production_claim": False,
        "result": "PASS",
        "region": "ap-south-1",
        "run_id": "cb-20260814-001",
        "commit_sha": "0123456789abcdef",
        "resources": {
            "dms_task_arn": "redacted:dms-task",
            "dms_checkpoint": "lsn:0/16B6C50",
            "iceberg_snapshot_id": "123456789",
            "generation_table": "changebridge-lab-generations",
            "cloudwatch_log_group": "/aws/changebridge/redacted",
        },
        "failure_tests": [
            "cdc_gap",
            "conflicting_replay",
            "worker_crash",
            "reconciliation_mismatch",
            "stale_cutover",
        ],
        "metrics": {"records_processed": 1000, "runtime_seconds": 42.1, "cost_usd": 1.25},
        "teardown": {"destroyed": True, "verified_at": "2026-08-14T12:00:00Z"},
    }
    payload["evidence_digest"] = digest(payload)
    return payload


def test_complete_aws_evidence_contract_passes() -> None:
    assert validate_aws_lab_evidence(valid_bundle()) == ()


def test_evidence_contract_fails_closed_after_mutation() -> None:
    payload = valid_bundle()
    payload["failure_tests"] = ["cdc_gap"]
    payload["production_claim"] = True
    errors = validate_aws_lab_evidence(payload)
    assert any("production_claim" in error for error in errors)
    assert any("failure tests missing" in error for error in errors)
    assert any("evidence_digest" in error for error in errors)

