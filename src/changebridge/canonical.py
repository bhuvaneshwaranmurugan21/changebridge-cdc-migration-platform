"""Deterministic encodings used by replay and reconciliation proofs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def canonical_json(value: Any) -> str:
    """Return a stable JSON representation without environment-dependent whitespace."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def table_digest(rows: Mapping[str, Mapping[str, Any]]) -> str:
    ordered: Sequence[tuple[str, Mapping[str, Any]]] = sorted(rows.items())
    return digest(ordered)
