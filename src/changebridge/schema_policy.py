"""Versioned, deterministic Stage 5 schema and primary-key policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, NoReturn, cast

from changebridge.contracts import schema_digest, semantic_digest

POLICY_ID = "changebridge.schema-policy"
POLICY_VERSION = "1.0.0"
SUPPORTED_CHANGE = "ADD_NULLABLE_NON_KEY_FIELD"


class SchemaPolicyError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise SchemaPolicyError(code, detail)


@dataclass(frozen=True, order=True)
class FieldDefinition:
    name: str
    data_type: str
    nullable: bool


@dataclass(frozen=True)
class PrimaryKeyField:
    ordinal: int
    name: str
    data_type: str


@dataclass(frozen=True)
class ContractIdentity:
    contract_id: str
    version: str
    digest: str


@dataclass(frozen=True)
class RegisteredSchema:
    identity: ContractIdentity
    source_table: str
    fields: tuple[FieldDefinition, ...]
    primary_key: tuple[PrimaryKeyField, ...]


@dataclass(frozen=True)
class SchemaDecision:
    decision_id: str
    decision_digest: str
    generation_id: str
    source_table: str
    previous: ContractIdentity
    candidate: ContractIdentity
    previous_primary_key: tuple[PrimaryKeyField, ...]
    candidate_primary_key: tuple[PrimaryKeyField, ...]
    policy_id: str
    policy_version: str
    policy_digest: str
    verdict: Literal["COMPATIBLE", "INCOMPATIBLE", "UNKNOWN"]
    reason_codes: tuple[str, ...]
    required_action: Literal["APPLY", "QUARANTINE", "REJECT"]
    added_fields: tuple[FieldDefinition, ...]

    def record(self) -> dict[str, Any]:
        value = asdict(self)
        value["previous_primary_key"] = [asdict(row) for row in self.previous_primary_key]
        value["candidate_primary_key"] = [asdict(row) for row in self.candidate_primary_key]
        value["added_fields"] = [asdict(row) for row in self.added_fields]
        return value


def _type_name(specification: Mapping[str, Any]) -> tuple[str, bool]:
    raw = specification.get("type")
    values = list(raw) if isinstance(raw, list) else [raw]
    if not values or any(not isinstance(value, str) for value in values):
        _fail("CB25S002_UNSUPPORTED_TYPE", repr(raw))
    typed_values = cast(list[str], values)
    nullable = "null" in typed_values
    concrete = sorted(value for value in typed_values if value != "null")
    if len(concrete) != 1 or concrete[0] not in {"integer", "number", "string", "boolean"}:
        _fail("CB25S002_UNSUPPORTED_TYPE", repr(raw))
    return concrete[0], nullable


def registered_schema(
    *,
    contract_id: str,
    version: str,
    source_table: str,
    schema: Mapping[str, Any],
    primary_key: tuple[str, ...],
) -> RegisteredSchema:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or not primary_key:
        _fail("CB25S003_INVALID_CONTRACT", contract_id)
    fields: list[FieldDefinition] = []
    field_map: dict[str, FieldDefinition] = {}
    for name, raw in properties.items():
        if not isinstance(name, str) or not isinstance(raw, Mapping):
            _fail("CB25S003_INVALID_CONTRACT", contract_id)
        data_type, nullable = _type_name(raw)
        field = FieldDefinition(name=name, data_type=data_type, nullable=nullable)
        fields.append(field)
        field_map[name] = field
    key: list[PrimaryKeyField] = []
    for ordinal, name in enumerate(primary_key):
        key_field = field_map.get(name)
        if key_field is None or key_field.nullable:
            _fail("CB25S004_INVALID_PRIMARY_KEY", name)
        key.append(PrimaryKeyField(ordinal=ordinal, name=name, data_type=key_field.data_type))
    return RegisteredSchema(
        identity=ContractIdentity(contract_id, version, schema_digest(schema)),
        source_table=source_table,
        fields=tuple(sorted(fields)),
        primary_key=tuple(key),
    )


class SchemaRegistry:
    def __init__(self) -> None:
        self._contracts: dict[tuple[str, str, str], RegisteredSchema] = {}

    def add(self, contract: RegisteredSchema) -> None:
        key = (
            contract.identity.contract_id,
            contract.identity.version,
            contract.identity.digest,
        )
        existing = self._contracts.get(key)
        if existing is not None and existing != contract:
            _fail("CB25S005_REGISTRY_CONFLICT", contract.identity.contract_id)
        self._contracts[key] = contract

    def resolve(self, identity: ContractIdentity) -> RegisteredSchema | None:
        return self._contracts.get((identity.contract_id, identity.version, identity.digest))


def policy_material() -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "compatible": [SUPPORTED_CHANGE, "EXACT_REPLAY"],
        "incompatible": [
            "FIELD_REMOVED",
            "FIELD_RENAMED",
            "TYPE_CHANGED",
            "NULLABILITY_NARROWED",
            "REQUIRED_FIELD_ADDED",
            "PRIMARY_KEY_CHANGED",
        ],
        "unknown": ["UNREGISTERED_IDENTITY", "POLICY_MISMATCH"],
    }


POLICY_DIGEST = semantic_digest(policy_material(), domain="stage25-schema-policy")


class SchemaPolicy:
    def __init__(self, registry: SchemaRegistry) -> None:
        self.registry = registry

    def decide(
        self,
        *,
        generation_id: str,
        source_table: str,
        previous: ContractIdentity,
        candidate: ContractIdentity,
        policy_digest: str = POLICY_DIGEST,
    ) -> SchemaDecision:
        old = self.registry.resolve(previous)
        new = self.registry.resolve(candidate)
        reasons: list[str] = []
        added: tuple[FieldDefinition, ...] = ()
        if policy_digest != POLICY_DIGEST:
            verdict: Literal["COMPATIBLE", "INCOMPATIBLE", "UNKNOWN"] = "UNKNOWN"
            reasons.append("CB25S010_POLICY_MISMATCH")
        elif old is None or new is None:
            verdict = "UNKNOWN"
            reasons.append("CB25S001_UNKNOWN_CONTRACT")
        elif old.source_table != source_table or new.source_table != source_table:
            verdict = "UNKNOWN"
            reasons.append("CB25S011_TABLE_IDENTITY_MISMATCH")
        else:
            old_fields = {field.name: field for field in old.fields}
            new_fields = {field.name: field for field in new.fields}
            removed = sorted(set(old_fields) - set(new_fields))
            new_names = sorted(set(new_fields) - set(old_fields))
            if old.primary_key != new.primary_key:
                reasons.append("CB25S020_PRIMARY_KEY_CHANGED")
            if removed:
                reasons.append("CB25S021_FIELD_REMOVED")
            for name in sorted(set(old_fields) & set(new_fields)):
                before, after = old_fields[name], new_fields[name]
                if before.data_type != after.data_type:
                    reasons.append("CB25S022_TYPE_CHANGED")
                if before.nullable and not after.nullable:
                    reasons.append("CB25S023_NULLABILITY_NARROWED")
            added = tuple(new_fields[name] for name in new_names)
            if any(not field.nullable for field in added):
                reasons.append("CB25S024_REQUIRED_FIELD_ADDED")
            verdict = "INCOMPATIBLE" if reasons else "COMPATIBLE"
        reasons = sorted(set(reasons))
        if verdict == "COMPATIBLE":
            action: Literal["APPLY", "QUARANTINE", "REJECT"] = "APPLY"
        elif verdict == "UNKNOWN":
            action = "QUARANTINE"
        else:
            action = "REJECT"
        old_key = () if old is None else old.primary_key
        new_key = () if new is None else new.primary_key
        material = {
            "generation_id": generation_id,
            "source_table": source_table,
            "previous": asdict(previous),
            "candidate": asdict(candidate),
            "previous_primary_key": [asdict(row) for row in old_key],
            "candidate_primary_key": [asdict(row) for row in new_key],
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "policy_digest": policy_digest,
            "verdict": verdict,
            "reason_codes": reasons,
            "required_action": action,
            "added_fields": [asdict(row) for row in added],
        }
        decision_digest = semantic_digest(material, domain="stage25-schema-decision")
        return SchemaDecision(
            decision_id=f"schema-decision-{decision_digest[:24]}",
            decision_digest=decision_digest,
            generation_id=generation_id,
            source_table=source_table,
            previous=previous,
            candidate=candidate,
            previous_primary_key=old_key,
            candidate_primary_key=new_key,
            policy_id=POLICY_ID,
            policy_version=POLICY_VERSION,
            policy_digest=policy_digest,
            verdict=verdict,
            reason_codes=tuple(reasons),
            required_action=action,
            added_fields=added,
        )


def assert_key_values_unchanged(event: Mapping[str, Any], decision: SchemaDecision) -> None:
    if event.get("operation") != "update":
        return
    before, after = event.get("before"), event.get("after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        _fail("CB25S030_INVALID_UPDATE_IMAGES", str(event.get("event_id")))
    if any(
        before.get(field.name) != after.get(field.name) for field in decision.candidate_primary_key
    ):
        _fail("CB25S031_PRIMARY_KEY_VALUE_CHANGED", str(event.get("event_id")))
