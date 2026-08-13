"""Cutover is a quality decision, never merely an orchestration step."""

from __future__ import annotations

from dataclasses import dataclass

from changebridge.reconciliation import ReconciliationReport
from changebridge.schema import CompatibilityResult


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    failures: tuple[str, ...]


def evaluate_cutover(
    report: ReconciliationReport,
    schema: CompatibilityResult,
    *,
    lag_seconds: float,
    max_lag_seconds: float,
    pre_migration_checks_passed: bool,
    rollback_generation_available: bool,
) -> GateResult:
    failures: list[str] = []
    if not report.matched:
        failures.append("reconciliation mismatch")
    if not schema.compatible:
        failures.append("breaking schema change")
    if lag_seconds > max_lag_seconds:
        failures.append(f"lag {lag_seconds:.3f}s exceeds {max_lag_seconds:.3f}s")
    if not pre_migration_checks_passed:
        failures.append("pre-migration checks failed")
    if not rollback_generation_available:
        failures.append("rollback generation unavailable")
    return GateResult(allowed=not failures, failures=tuple(failures))
