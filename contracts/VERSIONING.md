# Contract Versioning Policy

`contracts/catalog.json` is the machine-readable authority. Every writer emits an exact contract ID,
semantic version, schema URI, and contract digest. Readers accept only versions registered as
compatible; unknown versions and unknown fields are rejected and quarantined.

An additive optional field requires a new minor version. A new required field, type change, enum
contraction, rename, or removal requires a new major version. A semantic reinterpretation requires a
new contract ID. Enum expansion is reader-dependent and is compatible only after every affected
reader declares support. Filename similarity is never compatibility evidence.

Migration requires a deterministic converter whose source and target contract digests are recorded.
Deprecation requires a replacement contract ID and removal stage. Historical evidence is immutable:
Stage 1–3 receipts continue to validate against `schemas/stage-evidence.schema.json`; they are not
rewritten to the Stage 4 `stage_receipt` contract.

These rules are `DESIGN_ONLY` governance plus `LOCAL_VERIFIED` schema/oracle behavior. They do not
prove that a future DMS, Spark, Iceberg, or AWS adapter negotiates versions correctly.
