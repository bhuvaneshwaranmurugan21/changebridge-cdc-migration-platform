"""Schema compatibility policy: explicit and deliberately conservative."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    data_type: str
    nullable: bool


@dataclass(frozen=True)
class CompatibilityResult:
    compatible: bool
    reasons: tuple[str, ...]


def check_compatibility(
    previous: tuple[Field, ...], candidate: tuple[Field, ...]
) -> CompatibilityResult:
    """Allow nullable additions; block removals, type changes, and required additions."""

    old = {field.name: field for field in previous}
    new = {field.name: field for field in candidate}
    reasons: list[str] = []
    for name, field in old.items():
        if name not in new:
            reasons.append(f"removed field: {name}")
        elif new[name].data_type != field.data_type:
            reasons.append(f"type change: {name} {field.data_type}->{new[name].data_type}")
        elif field.nullable and not new[name].nullable:
            reasons.append(f"nullable field became required: {name}")
    for name, field in new.items():
        if name not in old and not field.nullable:
            reasons.append(f"required field added: {name}")
    return CompatibilityResult(compatible=not reasons, reasons=tuple(reasons))
