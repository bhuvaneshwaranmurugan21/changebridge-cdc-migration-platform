"""Typed PostgreSQL LSN and bounded CDC ordering primitives."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, NoReturn

_LSN = re.compile(r"^(?P<high>[0-9A-Fa-f]{1,8})/(?P<low>[0-9A-Fa-f]{1,8})$")


class CDCOrderingError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise CDCOrderingError(code, detail)


def parse_lsn(value: str) -> int:
    """Parse an unsigned PostgreSQL LSN into its 64-bit integer value."""

    match = _LSN.fullmatch(value)
    if match is None:
        _fail("CB24O001_INVALID_LSN", value)
    return (int(match.group("high"), 16) << 32) | int(match.group("low"), 16)


def normalize_lsn(value: str) -> str:
    parsed = parse_lsn(value)
    return f"{parsed >> 32:X}/{parsed & 0xFFFFFFFF:X}"


def event_lsn(event: Mapping[str, Any]) -> int:
    position = event.get("source_position")
    if not isinstance(position, Mapping) or position.get("kind") != "postgres_lsn":
        _fail("CB24O002_POSITION_KIND", repr(position))
    value = position.get("value")
    if not isinstance(value, str):
        _fail("CB24O001_INVALID_LSN", repr(value))
    return parse_lsn(value)


def event_order_key(event: Mapping[str, Any]) -> tuple[int, int, int, str]:
    try:
        transaction_sequence = int(event["transaction_sequence"])
        event_sequence = int(event["event_sequence"])
        event_id = str(event["event_id"])
    except (KeyError, TypeError, ValueError) as exc:
        _fail("CB24O003_SEQUENCE_MISSING", type(exc).__name__)
    if transaction_sequence < 0 or event_sequence < 1:
        _fail("CB24O004_SEQUENCE_RANGE", f"{transaction_sequence}:{event_sequence}")
    return (event_lsn(event), transaction_sequence, event_sequence, event_id)


def admit_interval(events: list[dict[str, Any]], previous: str, terminal: str) -> None:
    lower = parse_lsn(previous)
    upper = parse_lsn(terminal)
    if upper <= lower:
        _fail("CB24O005_INTERVAL_REGRESSION", f"{previous}->{terminal}")
    for event in events:
        position = event_lsn(event)
        if position <= lower or position > upper:
            _fail(
                "CB24O006_EVENT_OUTSIDE_INTERVAL",
                f"{event.get('event_id')}:{normalize_lsn(str(event['source_position']['value']))}",
            )


def ordered_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(events, key=event_order_key)
    seen: set[tuple[str, int]] = set()
    for event in ordered:
        identity = (str(event.get("transaction_id")), int(event.get("event_sequence", 0)))
        if identity in seen:
            _fail("CB24O007_DUPLICATE_SEQUENCE", repr(identity))
        seen.add(identity)
    return ordered
