"""Durable proof-gated publication, fallback, and rollback controls."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn, cast

from changebridge.contracts import semantic_digest
from changebridge.proof_gates import REQUIRED_GATES, assemble_manifest, validate_gate


class PublicationError(RuntimeError):
    """Stable fail-closed Stage 7 diagnostic."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class AmbiguousPublication(PublicationError):
    """The request may have committed; callers must reconcile by attempt ID."""


def _fail(code: str, detail: str) -> NoReturn:
    raise PublicationError(code, detail)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def validate_proof_manifest(manifest: Mapping[str, Any]) -> None:
    gates = manifest.get("gates")
    if not isinstance(gates, list):
        _fail("CB27P001_PROOF_INVALID", "gates")
    for gate in gates:
        if not isinstance(gate, Mapping):
            _fail("CB27P001_PROOF_INVALID", "gate")
        validate_gate(gate)
    if tuple(str(gate["gate_id"]) for gate in gates) != REQUIRED_GATES:
        _fail("CB27P002_GATE_SET_INVALID", "order-or-membership")
    rebuilt = assemble_manifest(
        gates,
        generation_id=str(manifest.get("generation_id")),
        frontier=str(manifest.get("frontier", {}).get("value")),
        schema_set_digest=str(manifest.get("schema_set_digest")),
        input_revision=int(manifest.get("input_revision", -1)),
        seal_digest=str(manifest.get("seal_digest")),
    )
    if rebuilt != dict(manifest):
        _fail("CB27P003_PROOF_DIGEST", str(manifest.get("proof_manifest_digest")))


def publication_binding_manifest(
    *,
    accepted_manifest: Mapping[str, Any],
    execution_manifest: Mapping[str, Any],
    table_map: Mapping[str, Mapping[str, Any]],
    accepted_reconciliation_digest: str,
    execution_reconciliation_digest: str,
) -> dict[str, Any]:
    """Bind a fresh physical materialization to the accepted logical proof."""

    validate_proof_manifest(accepted_manifest)
    validate_proof_manifest(execution_manifest)
    for field in ("generation_id", "frontier", "schema_set_digest"):
        if accepted_manifest[field] != execution_manifest[field]:
            _fail("CB27B001_PREDECESSOR_MISMATCH", field)
    if accepted_reconciliation_digest != execution_reconciliation_digest:
        _fail("CB27B002_LOGICAL_RECONCILIATION_MISMATCH", execution_reconciliation_digest)
    if set(table_map) != {"order_items", "orders"}:
        _fail("CB27B003_TABLE_MAP_INCOMPLETE", repr(sorted(table_map)))
    for table, binding in table_map.items():
        required = {"identifier", "snapshot_id", "manifest_list_digest", "row_count"}
        if set(binding) != required or int(binding["row_count"]) < 0:
            _fail("CB27B004_TABLE_BINDING_INVALID", table)
    table_map_digest = semantic_digest(table_map, domain="stage27-table-map")
    body: dict[str, Any] = {
        "record_type": "publication_binding_manifest",
        "contract_version": "1.0.0",
        "generation_id": execution_manifest["generation_id"],
        "frontier": execution_manifest["frontier"],
        "schema_set_digest": execution_manifest["schema_set_digest"],
        "accepted_proof_manifest_digest": accepted_manifest["proof_manifest_digest"],
        "execution_proof_manifest_digest": execution_manifest["proof_manifest_digest"],
        "accepted_reconciliation_digest": accepted_reconciliation_digest,
        "execution_reconciliation_digest": execution_reconciliation_digest,
        "gate_ids": list(REQUIRED_GATES),
        "table_map": dict(table_map),
        "table_map_digest": table_map_digest,
        "physical_identity_relation": "FRESH_EXECUTION_BOUND_MATERIALIZATION",
        "reuses_vanished_stage6_snapshots": False,
    }
    return {
        **body,
        "publication_binding_digest": semantic_digest(
            body, domain="stage27-publication-binding"
        ),
    }


class PublicationStore:
    """SQLite reference authority with a clock that survives pointer absence."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS publication_clock(
              product_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
              route TEXT NOT NULL CHECK(route IN ('SOURCE_FALLBACK','GENERATION')),
              CHECK(revision >= 0));
            CREATE TABLE IF NOT EXISTS active_pointer(
              product_id TEXT PRIMARY KEY REFERENCES publication_clock(product_id),
              generation_id TEXT NOT NULL, revision INTEGER NOT NULL,
              attempt_id TEXT NOT NULL, proof_manifest_digest TEXT NOT NULL,
              table_map_digest TEXT NOT NULL, publication_binding_digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS generations(
              generation_id TEXT PRIMARY KEY, frontier_json TEXT NOT NULL,
              schema_set_digest TEXT NOT NULL, proof_manifest_digest TEXT NOT NULL,
              publication_binding_digest TEXT NOT NULL, table_map_json TEXT NOT NULL,
              table_map_digest TEXT NOT NULL, consumer_contract TEXT NOT NULL,
              state TEXT NOT NULL, retained INTEGER NOT NULL, readable INTEGER NOT NULL,
              retired INTEGER NOT NULL, evidence_valid INTEGER NOT NULL,
              ever_published INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(
              attempt_id TEXT PRIMARY KEY, action TEXT NOT NULL,
              payload_digest TEXT NOT NULL, product_id TEXT NOT NULL,
              expected_revision INTEGER NOT NULL, verdict TEXT NOT NULL,
              resulting_revision INTEGER, receipt_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
              event_id TEXT PRIMARY KEY, product_id TEXT NOT NULL,
              attempt_id TEXT NOT NULL, action TEXT NOT NULL,
              from_revision INTEGER NOT NULL, to_revision INTEGER NOT NULL,
              from_generation_id TEXT, to_generation_id TEXT,
              decision_digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS consumer_pins(
              pin_id TEXT PRIMARY KEY, product_id TEXT NOT NULL,
              revision INTEGER NOT NULL, route TEXT NOT NULL,
              generation_id TEXT, proof_manifest_digest TEXT,
              table_map_digest TEXT, pin_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS orchestration_runs(
              run_id TEXT PRIMARY KEY, product_id TEXT NOT NULL,
              state TEXT NOT NULL, revision INTEGER NOT NULL,
              last_attempt_id TEXT, detail_json TEXT NOT NULL);
            """
        )

    def __enter__(self) -> PublicationStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.connection.close()

    def initialize_product(self, product_id: str) -> dict[str, Any]:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO publication_clock VALUES (?,0,'SOURCE_FALLBACK')",
                (product_id,),
            )
        return self.current(product_id)

    def current(self, product_id: str) -> dict[str, Any]:
        clock = self.connection.execute(
            "SELECT * FROM publication_clock WHERE product_id=?", (product_id,)
        ).fetchone()
        if clock is None:
            _fail("CB27C001_PRODUCT_UNKNOWN", product_id)
        pointer = self.connection.execute(
            "SELECT * FROM active_pointer WHERE product_id=?", (product_id,)
        ).fetchone()
        result = dict(clock)
        result["pointer"] = None if pointer is None else dict(pointer)
        if (result["route"] == "SOURCE_FALLBACK") != (pointer is None):
            _fail("CB27C002_POINTER_CLOCK_INCONSISTENT", product_id)
        return result

    def register_generation(
        self,
        binding: Mapping[str, Any],
        *,
        consumer_contract: str,
    ) -> dict[str, Any]:
        body = {key: value for key, value in binding.items() if key != "publication_binding_digest"}
        if semantic_digest(body, domain="stage27-publication-binding") != binding.get(
            "publication_binding_digest"
        ):
            _fail("CB27B005_BINDING_DIGEST", str(binding.get("generation_id")))
        values = (
            binding["generation_id"],
            _json(binding["frontier"]),
            binding["schema_set_digest"],
            binding["execution_proof_manifest_digest"],
            binding["publication_binding_digest"],
            _json(binding["table_map"]),
            binding["table_map_digest"],
            consumer_contract,
            "PROVEN",
            1,
            1,
            0,
            1,
            0,
        )
        existing = self.generation(str(binding["generation_id"]), required=False)
        if existing is not None:
            comparable = (
                existing["frontier_json"],
                existing["schema_set_digest"],
                existing["proof_manifest_digest"],
                existing["publication_binding_digest"],
                existing["table_map_json"],
                existing["table_map_digest"],
                existing["consumer_contract"],
            )
            if comparable != values[1:8]:
                _fail("CB27B006_GENERATION_BINDING_CONFLICT", str(binding["generation_id"]))
            return existing
        with self.connection:
            self.connection.execute(
                "INSERT INTO generations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values
            )
        result = self.generation(str(binding["generation_id"]))
        assert result is not None
        return result

    def generation(self, generation_id: str, *, required: bool = True) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM generations WHERE generation_id=?", (generation_id,)
        ).fetchone()
        if row is None:
            if required:
                _fail("CB27P004_GENERATION_UNKNOWN", generation_id)
            return None
        return dict(row)

    def _prior_attempt(self, attempt_id: str, payload_digest: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        if result["payload_digest"] != payload_digest:
            _fail("CB27P005_ATTEMPT_REPLAY_CONFLICT", attempt_id)
        return cast(dict[str, Any], json.loads(result["receipt_json"]))

    def _eligible(self, generation_id: str, *, rollback: bool = False) -> dict[str, Any]:
        generation = self.generation(generation_id)
        assert generation is not None
        allowed_state = generation["state"] in ({"PROVEN", "PUBLISHED"} if rollback else {"PROVEN"})
        flags = all(
            (
                allowed_state,
                generation["retained"] == 1,
                generation["readable"] == 1,
                generation["retired"] == 0,
                generation["evidence_valid"] == 1,
                not rollback or generation["ever_published"] == 1,
            )
        )
        if not flags:
            _fail("CB27P006_GENERATION_INELIGIBLE", generation_id)
        return generation

    def publish(
        self,
        *,
        product_id: str,
        generation_id: str,
        expected_revision: int,
        attempt_id: str,
        authorization: str,
        lose_acknowledgement: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "action": "PUBLISH",
            "product_id": product_id,
            "generation_id": generation_id,
            "expected_revision": expected_revision,
            "authorization": authorization,
        }
        digest = semantic_digest(payload, domain="stage27-publication-attempt")
        prior = self._prior_attempt(attempt_id, digest)
        if prior is not None:
            return prior
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            current = self.current(product_id)
            if int(current["revision"]) != expected_revision:
                _fail("CB27P007_STALE_REVISION", f"{expected_revision}!={current['revision']}")
            generation = self._eligible(generation_id)
            new_revision = expected_revision + 1
            receipt = {
                "attempt_id": attempt_id,
                "action": "PUBLISH",
                "verdict": "PUBLISHED",
                "product_id": product_id,
                "generation_id": generation_id,
                "prior_generation_id": None
                if current["pointer"] is None
                else current["pointer"]["generation_id"],
                "expected_revision": expected_revision,
                "resulting_revision": new_revision,
                "proof_manifest_digest": generation["proof_manifest_digest"],
                "table_map_digest": generation["table_map_digest"],
                "publication_binding_digest": generation["publication_binding_digest"],
            }
            self.connection.execute(
                "UPDATE publication_clock SET revision=?,route='GENERATION' WHERE product_id=?",
                (new_revision, product_id),
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO active_pointer VALUES (?,?,?,?,?,?,?)",
                (
                    product_id,
                    generation_id,
                    new_revision,
                    attempt_id,
                    generation["proof_manifest_digest"],
                    generation["table_map_digest"],
                    generation["publication_binding_digest"],
                ),
            )
            self.connection.execute(
                "UPDATE generations SET state='PUBLISHED',ever_published=1 WHERE generation_id=?",
                (generation_id,),
            )
            self._insert_attempt(attempt_id, payload, digest, receipt)
            self._insert_event(receipt)
            self.connection.execute("COMMIT")
        except Exception:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise
        if lose_acknowledgement:
            raise AmbiguousPublication("CB27P008_ACK_AMBIGUOUS", attempt_id)
        return receipt

    def first_publication_fallback(
        self,
        *,
        product_id: str,
        expected_revision: int,
        attempt_id: str,
        authorization: str,
        lose_acknowledgement: bool = False,
    ) -> dict[str, Any]:
        if not authorization:
            _fail("CB27F001_AUTHORIZATION_REQUIRED", attempt_id)
        payload = {
            "action": "FIRST_PUBLICATION_FALLBACK",
            "product_id": product_id,
            "expected_revision": expected_revision,
            "authorization": authorization,
        }
        digest = semantic_digest(payload, domain="stage27-publication-attempt")
        prior = self._prior_attempt(attempt_id, digest)
        if prior is not None:
            return prior
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            current = self.current(product_id)
            pointer = current["pointer"]
            if int(current["revision"]) != expected_revision or pointer is None:
                _fail("CB27P007_STALE_REVISION", str(expected_revision))
            new_revision = expected_revision + 1
            receipt = {
                "attempt_id": attempt_id,
                "action": "FIRST_PUBLICATION_FALLBACK",
                "verdict": "SOURCE_FALLBACK_VERIFIED",
                "product_id": product_id,
                "generation_id": None,
                "prior_generation_id": pointer["generation_id"],
                "expected_revision": expected_revision,
                "resulting_revision": new_revision,
                "represents_prior_published_generation": False,
            }
            self.connection.execute(
                "DELETE FROM active_pointer WHERE product_id=? AND revision=?",
                (product_id, expected_revision),
            )
            if self.connection.execute("SELECT changes()").fetchone()[0] != 1:
                _fail("CB27F002_POINTER_OUTCOME_UNRESOLVED", product_id)
            self.connection.execute(
                "UPDATE publication_clock SET revision=?,route='SOURCE_FALLBACK' "
                "WHERE product_id=?",
                (new_revision, product_id),
            )
            self._insert_attempt(attempt_id, payload, digest, receipt)
            self._insert_event(receipt)
            self.connection.execute("COMMIT")
        except Exception:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise
        if lose_acknowledgement:
            raise AmbiguousPublication("CB27P008_ACK_AMBIGUOUS", attempt_id)
        return receipt

    def rollback(
        self,
        *,
        product_id: str,
        target_generation_id: str,
        expected_revision: int,
        attempt_id: str,
        authorization: str,
    ) -> dict[str, Any]:
        if not authorization:
            _fail("CB27R001_AUTHORIZATION_REQUIRED", attempt_id)
        payload = {
            "action": "ROLLBACK",
            "product_id": product_id,
            "target_generation_id": target_generation_id,
            "expected_revision": expected_revision,
            "authorization": authorization,
        }
        digest = semantic_digest(payload, domain="stage27-publication-attempt")
        prior = self._prior_attempt(attempt_id, digest)
        if prior is not None:
            return prior
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            current = self.current(product_id)
            pointer = current["pointer"]
            if int(current["revision"]) != expected_revision or pointer is None:
                _fail("CB27P007_STALE_REVISION", str(expected_revision))
            if pointer["generation_id"] == target_generation_id:
                _fail("CB27R002_TARGET_ALREADY_ACTIVE", target_generation_id)
            target = self._eligible(target_generation_id, rollback=True)
            new_revision = expected_revision + 1
            receipt = {
                "attempt_id": attempt_id,
                "action": "ROLLBACK",
                "verdict": "ROLLBACK_VERIFIED",
                "product_id": product_id,
                "generation_id": target_generation_id,
                "prior_generation_id": pointer["generation_id"],
                "expected_revision": expected_revision,
                "resulting_revision": new_revision,
                "proof_manifest_digest": target["proof_manifest_digest"],
                "table_map_digest": target["table_map_digest"],
                "publication_binding_digest": target["publication_binding_digest"],
            }
            self.connection.execute(
                "UPDATE publication_clock SET revision=? WHERE product_id=?",
                (new_revision, product_id),
            )
            self.connection.execute(
                "UPDATE active_pointer SET generation_id=?,revision=?,attempt_id=?,"
                "proof_manifest_digest=?,table_map_digest=?,publication_binding_digest=? "
                "WHERE product_id=?",
                (
                    target_generation_id,
                    new_revision,
                    attempt_id,
                    target["proof_manifest_digest"],
                    target["table_map_digest"],
                    target["publication_binding_digest"],
                    product_id,
                ),
            )
            self.connection.execute(
                "UPDATE generations SET state='ROLLED_BACK' WHERE generation_id=?",
                (pointer["generation_id"],),
            )
            self._insert_attempt(attempt_id, payload, digest, receipt)
            self._insert_event(receipt)
            self.connection.execute("COMMIT")
        except Exception:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise
        return receipt

    def reconcile_attempt(self, attempt_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT receipt_json FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            _fail("CB27P009_ATTEMPT_OUTCOME_UNKNOWN", attempt_id)
        receipt = cast(dict[str, Any], json.loads(row["receipt_json"]))
        current = self.current(str(receipt["product_id"]))
        if int(current["revision"]) < int(receipt["resulting_revision"]):
            _fail("CB27P010_ATTEMPT_CLOCK_DIVERGENCE", attempt_id)
        return receipt

    def pin(self, product_id: str, pin_id: str) -> dict[str, Any]:
        current = self.current(product_id)
        pointer = current["pointer"]
        body = {
            "pin_id": pin_id,
            "product_id": product_id,
            "revision": current["revision"],
            "route": current["route"],
            "generation_id": None if pointer is None else pointer["generation_id"],
            "proof_manifest_digest": None
            if pointer is None
            else pointer["proof_manifest_digest"],
            "table_map_digest": None if pointer is None else pointer["table_map_digest"],
            "table_map": None,
        }
        if pointer is not None:
            generation = self.generation(str(pointer["generation_id"]))
            assert generation is not None
            body["table_map"] = json.loads(generation["table_map_json"])
        existing = self.connection.execute(
            "SELECT pin_json FROM consumer_pins WHERE pin_id=?", (pin_id,)
        ).fetchone()
        payload = _json(body)
        if existing is not None:
            if existing["pin_json"] != payload:
                _fail("CB27C003_PIN_CONFLICT", pin_id)
            return body
        with self.connection:
            self.connection.execute(
                "INSERT INTO consumer_pins VALUES (?,?,?,?,?,?,?,?)",
                (
                    pin_id,
                    product_id,
                    body["revision"],
                    body["route"],
                    body["generation_id"],
                    body["proof_manifest_digest"],
                    body["table_map_digest"],
                    payload,
                ),
            )
        return body

    def set_eligibility(self, generation_id: str, **flags: bool) -> None:
        allowed = {"retained", "readable", "retired", "evidence_valid"}
        if not flags or not set(flags) <= allowed:
            raise ValueError("unsupported eligibility flag")
        assignments = ",".join(f"{key}=?" for key in sorted(flags))
        values = [int(flags[key]) for key in sorted(flags)] + [generation_id]
        with self.connection:
            self.connection.execute(
                f"UPDATE generations SET {assignments} WHERE generation_id=?", values
            )

    def start_run(self, run_id: str, product_id: str) -> dict[str, Any]:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO orchestration_runs VALUES (?,?,'PLANNED',0,NULL,'{}')",
                (run_id, product_id),
            )
        return self.run(run_id)

    def transition_run(
        self,
        run_id: str,
        *,
        expected_revision: int,
        to_state: str,
        attempt_id: str | None,
        detail: Mapping[str, Any],
    ) -> dict[str, Any]:
        allowed = {
            ("PLANNED", "ELIGIBLE"),
            ("ELIGIBLE", "PUBLISHING"),
            ("PUBLISHING", "VERIFYING"),
            ("VERIFYING", "ACTIVE"),
            ("VERIFYING", "INCIDENT"),
            ("ACTIVE", "INCIDENT"),
            ("INCIDENT", "RECOVERING"),
            ("RECOVERING", "SOURCE_FALLBACK_VERIFIED"),
            ("RECOVERING", "ROLLBACK_VERIFIED"),
        }
        run = self.run(run_id)
        if int(run["revision"]) != expected_revision:
            _fail("CB27O001_STALE_RUN_REVISION", run_id)
        if (str(run["state"]), to_state) not in allowed:
            _fail("CB27O002_ILLEGAL_RUN_TRANSITION", f"{run['state']}->{to_state}")
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE orchestration_runs SET state=?,revision=revision+1,last_attempt_id=?,"
                "detail_json=? WHERE run_id=? AND revision=?",
                (to_state, attempt_id, _json(detail), run_id, expected_revision),
            )
            if cursor.rowcount != 1:
                _fail("CB27O001_STALE_RUN_REVISION", run_id)
        return self.run(run_id)

    def run(self, run_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM orchestration_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            _fail("CB27O003_RUN_UNKNOWN", run_id)
        return dict(row)

    def _insert_attempt(
        self,
        attempt_id: str,
        payload: Mapping[str, Any],
        payload_digest: str,
        receipt: Mapping[str, Any],
    ) -> None:
        self.connection.execute(
            "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?)",
            (
                attempt_id,
                payload["action"],
                payload_digest,
                payload["product_id"],
                payload["expected_revision"],
                receipt["verdict"],
                receipt["resulting_revision"],
                _json(receipt),
            ),
        )

    def _insert_event(self, receipt: Mapping[str, Any]) -> None:
        event_body = {
            "attempt_id": receipt["attempt_id"],
            "action": receipt["action"],
            "from_revision": receipt["expected_revision"],
            "to_revision": receipt["resulting_revision"],
            "from_generation_id": receipt.get("prior_generation_id"),
            "to_generation_id": receipt.get("generation_id"),
        }
        decision_digest = semantic_digest(event_body, domain="stage27-publication-event")
        self.connection.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
            (
                decision_digest,
                receipt["product_id"],
                receipt["attempt_id"],
                receipt["action"],
                receipt["expected_revision"],
                receipt["resulting_revision"],
                receipt.get("prior_generation_id"),
                receipt.get("generation_id"),
                decision_digest,
            ),
        )
