# ChangeBridge current-state audit

## Audit identity and scope

- Repository: `bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform`
- Audited base commit: `6081230f222b6efb2468a010b4dddfb13b90e2f6`
- Audited tree: `78d896e3056921d64a49fb11eaa8f73fdd5c444f`
- Stage run: `cb-p1-s1-20260917T073557Z-6081230`
- Scope: Part 1, Stage 1 exact-state and isolation audit only

No application behavior, infrastructure behavior, dependency declaration, workflow, AWS state, release, tag, history, or other project was changed. The unmerged historical draft PR #1 was inventoried but excluded from the audited `main` baseline.

## Exact starting state

The audit used a fresh, non-shallow clone of `main`. `HEAD` and `origin/main` both resolved to the audited commit. The starting worktree was clean, no interrupted Git operation or submodule existed, and the repository identity matched the authenticated GitHub repository. Branch-protection detail was not accessible to the installed integration; repository rulesets were empty.

## Repository topology and inventory

The audited tree has **33 tracked files**, all regular non-executable files, with no symlinks or binary files. Two independent inventory runs produced the same procedure digest `1ae17a25a05e8798f9244b90e5c44c1d2af921a5a58dc328a68c1ef4c67bad8a`. The historical 32-file statement is true for implementation commit `6df84bf...` and remains true through `98037af...`; `6081230...` added the 33rd file, `.github/workflows/aws-oidc-identity.yml`.

The repository contains a SQLite reference kernel, four pytest files, three GitHub Actions workflows, Terraform declarations, a thin Spark adapter, one JSON contract, architecture/failure/runbook/claims documentation, and one committed local-simulation artifact. There are no tags or releases.

## History, branches, PRs, and workflows

`main` has six commits. A separate branch, `agent/production-grade-foundation`, contains one unmerged commit and open draft PR #1. It changes eleven files and is not used as proof for this audit.

- `CI` installs declared development dependencies on an ephemeral runner, runs Ruff, mypy, pytest/coverage, and regenerates local evidence.
- `Infrastructure` runs Terraform formatting, provider initialization with the backend disabled, and validation; Stage 1 did not run it locally because Terraform is absent and installation is prohibited.
- `AWS OIDC Identity Check` assumes a repository-specific role and calls STS. Stage 1 classified it unsafe and did not trigger it.

The exact audited `main` commit has a successful historical CI run (`31722053980`) and successful historical OIDC run (`31722054083`). These remote observations do not replace the Stage 1 safety boundary.

## Historical baseline reconciliation

Confirmed strengths:

- The SQLite oracle implements generation lifecycle, snapshot load, contiguous frontiers, batch/transaction replay identity, tombstones, transactional rollback on injected failure, schema compatibility checks, count-plus-digest reconciliation, proof gates, and compare-and-swap activation.
- The simulator executed twice and reproduced the committed evidence byte-for-byte: SHA-256 `13ff5b8ffa5c4d98193e0363665cd2fe5a8482ca4963f959f99ab88bbc79eb24` with 13/13 checks passing.
- The README and claim registry explicitly withhold managed AWS runtime, throughput, availability, and cost claims.
- Current tree and reachable history contain no other portfolio project names or obsolete `changebridge-cdc-lakehouse-platform` name.

Material limitations and contradictions:

- `docs/failure-lab.md` documents 11 rows while the executable simulator contains 13 checks.
- The Spark adapter validates five columns and counts rows; it performs no Iceberg write/MERGE, delete application, checkpointing, or idempotency transaction.
- Step Functions appears in the architecture narrative, but no state-machine definition, Terraform resource, test, or runtime evidence exists.
- Terraform is a partial reference topology: it lacks a source database, replication instance, Glue job, Step Functions, budget, execution lease/TTL, and proven teardown.
- Reconciliation is a local full-table canonical digest with no partitioned/keyed localization or scale evidence.
- Rollback is described and can be modeled through generic CAS activation, but no explicit rollback API or simulator scenario exists.
- The committed simulation artifact is reproducible but does not embed commit/run/tool provenance.

## Safe validation baseline

Safe Python compilation passed. The deterministic local simulation passed twice, and both outputs matched the committed artifact exactly. `pytest`, Ruff, mypy, and Terraform were absent and were not installed. Pytest/coverage, lint, type checking, and Terraform formatting are therefore `BLOCKED` locally. Terraform provider initialization/validation and AWS OIDC are `UNSAFE_TO_RUN` under the Stage 1 authorization. No validation changed the repository or contacted AWS.

## Isolation, provenance, public claims, and sensitive data

No cross-project or obsolete-name match was found in the current tree or reachable history. Terraform names are ChangeBridge-prefixed; deployed resources were not inspected. The generic secret pattern produced one false positive on the GitHub OIDC permission key. No credential-like value or suspicious tracked filename was found. Normal public Git commit metadata contains a personal author/committer email; only a redacted digest is recorded.

The highest-risk public wording is the “production-shaped Spark adapter” label, because the current adapter stops at schema-shape validation and a row count. The Step Functions production-path statement is unbound. These claims are findings only; Stage 1 intentionally does not rewrite them.

## Evidence map

- `repository_identity.json` — exact identity, topology, and clean starting state
- `repository_inventory.json` — deterministic per-file inventory and digests
- `baseline_claims_matrix.json` — historical/current capability adjudication
- `validation_baseline.json` — safe, blocked, and unsafe validation outcomes
- `isolation_audit.json` — cross-project, namespace, provenance, and sensitive-data findings
- `public_claims_inventory.json` — material public-claim support classifications
- `substage_receipts.json` — trust-boundary completion state
- `artifact_manifest.json` — non-recursive artifact integrity map
- `stage_receipt.json` — Stage 1 acceptance and closure contract

## Exact continuation checkpoint

The audited implementation truth is base commit `6081230f222b6efb2468a010b4dddfb13b90e2f6`. Stage 1 publication is isolated on `part1-stage1-exact-state-audit`. The repository receipt binds the immutable audit payload; exact PR-head CI and merged-`main` identity are bound externally in the closed PR and the post-merge continuation checkpoint to avoid a self-referential commit loop. Part 1 Stage 2 must not start without that exact merged checkpoint.
