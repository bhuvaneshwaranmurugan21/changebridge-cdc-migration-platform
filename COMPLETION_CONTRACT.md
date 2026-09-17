# ChangeBridge Completion Contract

## Status and scope

This document defines the conditions that ChangeBridge must eventually satisfy to be called
complete. It does not assert that those conditions are currently satisfied. Current claims and
their evidence boundaries are published in [`CLAIMS.md`](CLAIMS.md).

ChangeBridge Part 1 Stage 2 establishes completion and claim authority. Runtime implementation,
managed AWS execution, performance measurement, cutover, rollback, and release completion remain
owned by later stages.

## Central proposition

For a migration generation `G`:

```text
G = immutable snapshot at frontier S
  + contiguous, transaction-preserving CDC interval (S, F]
  + deterministic proof set evaluated at F
  + compare-and-swap publication of the proven generation
```

ChangeBridge is complete only when every mandatory requirement in
`requirements/completion-requirements.json` is satisfied by its minimum evidence class and the
final release bindings refer to one immutable repository and run state.

## Non-substitutable completion conditions

The following do not establish completion by themselves:

- a running DMS task;
- a successful snapshot or row-count comparison;
- storage objects or Iceberg tables existing;
- Terraform formatting, validation, or a plan;
- a green workflow not bound to the reviewed commit;
- a locally passing correctness oracle;
- a later successful run that does not explain and supersede an earlier failed gate;
- a percentage of checklist items completed.

Every failed mandatory gate remains failed until its root cause is corrected and the focused and
dependent validation layers are rerun.

## Normative vocabulary

- **MUST / MUST NOT** — mandatory; failure blocks the owning stage and project completion.
- **SHOULD** — expected; deviation requires an explicit rationale and review record.
- **MAY** — optional and non-blocking.

## Implementation-state vocabulary

- **IMPLEMENTED** — code or infrastructure exists; no proof is implied.
- **TESTED** — a named test exercises a behavior in a stated environment.
- **LOCAL_VERIFIED** — reproducible local evidence passes at an exact repository state.
- **AWS_VERIFIED** — managed AWS evidence satisfies lineage, failure, recovery, and teardown rules.
- **MEASURED** — raw results from a bounded workload are bound to an exact run and environment.
- **EXTRAPOLATED** — a model is derived from named measurements, method, and assumptions.
- **RELEASED** — final main, CI, annotated tag, assets, checksums, and completion receipt agree.

Implementation state is not permission to make a broader public claim.

## Public evidence labels

Every material public claim uses exactly one label:

### `DESIGN_ONLY`

The claim describes a versioned contract, ADR, topology, or intended behavior. It must not use
wording that implies executable or managed-runtime proof.

### `LOCAL_VERIFIED`

The claim is supported by a reproducible command or test, an exact commit or tree, deterministic
local evidence, and an explicit environment limitation. Local mocks, shape validation, and
reference engines cannot be presented as managed-service behavior.

### `AWS_VERIFIED`

The claim requires an exact repository commit, managed run ID, sanitized account/region identity,
resource inventory, logs and results, relevant failure/recovery proof, and teardown or residual
state. Terraform validation, screenshots alone, OIDC identity, and unbound historical output are
insufficient.

### `MEASURED`

The claim requires an immutable workload definition, raw observations, calculation method,
environment, timestamps, exact commit/run lineage, and stated bounds or uncertainty. An
unattributed number is not a measurement.

### `EXTRAPOLATED`

The claim requires a named measured basis, transformation method, assumptions, range, and
sensitivity or limitation. It must never be written as observed behavior.

### `UNCLAIMED`

No capability proof is asserted. The wording may describe a missing capability, future target, or
limitation, but not a present-tense proven behavior.

## Consumer-consistency boundary

ChangeBridge targets consumer-visible consistency by building an isolated generation, proving it,
and publishing one versioned active-generation pointer. This is not a claim of atomic transactions
across multiple Iceberg tables. Cross-table storage atomicity may be claimed only if a later
implementation and managed proof establish it explicitly.

## Authority order

When artifacts disagree, the stage fails closed. Authority is ordered as follows:

1. `requirements/completion-requirements.json` defines obligations.
2. Accepted contracts and ADRs define semantics.
3. Implementation at an exact commit defines behavior that exists.
4. Tests and evidence bound to that commit/run define behavior that is proven.
5. `claims/claims.json` defines approved public wording and evidence labels.
6. Rendered documentation is a projection of those sources and cannot override them.

The human-readable requirement and claim documents are generated views. The machine-readable
registries are authoritative.

## Evidence invalidation

Evidence and claims become stale when any of the following occurs:

- their producing commit is no longer the relevant implementation state;
- referenced files, tests, workload, semantics, or environment change;
- a proof artifact is missing or its digest changes;
- managed run lineage cannot be resolved;
- a stronger contradictory result appears;
- a declared review expiry or invalidation condition is met.

Stale evidence is not silently retained. The claim is downgraded or marked `UNCLAIMED` until the
required proof is reproduced.

## Completion authority

Project completion requires all mandatory requirements, exact claim/evidence alignment, managed
happy-path and failure/recovery proof, bounded measurements, operational and security closure,
teardown verification, and mutual binding of final main, CI, annotated tag, assets, checksums, and
`PROJECT_COMPLETION_VERIFIED`.

Until that point, ChangeBridge remains incomplete regardless of documentation quality or local
test coverage.
