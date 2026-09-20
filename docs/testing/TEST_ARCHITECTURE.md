# Test Architecture

Generated from `testing/test-layers.json`; each layer has an explicit proof boundary.

| Layer | Proves | Does not prove | CI | Future owner |
|---|---|---|---|---|
| `unit` | Pure canonicalization, parsing, and predicate branches. | Does not prove adapter or service behavior. | every PR | `part2-runtime` |
| `generative_property` | Canonicalization and ordering properties over generated semantic inputs. | Finite generated examples do not prove all values or managed transports. | every PR | `part2-runtime` |
| `state_machine_model` | Lifecycle, checkpoint, proof, publication, and rollback transition legality. | Does not prove distributed storage atomicity. | every PR | `part2-runtime` |
| `contract` | JSON Schema structure plus semantic cross-field rules. | Does not prove producers emit conforming records. | every PR | `part2-runtime` |
| `differential` | Future adapters produce the same canonical state and proof digests as the local oracle. | Stage 4 defines but does not execute adapters. | Part 2 CI | `part2-runtime` |
| `integration` | Runtime components exchange versioned records across real local boundaries. | Local integration does not prove AWS services. | Part 2 CI | `part2-runtime` |
| `failure` | Crash, retry, duplicate, conflict, stale writer, and rollback outcomes. | Local injection does not establish managed failure rates. | every PR | `part2-runtime` |
| `infrastructure_security` | Future least privilege, encryption, isolation, lifecycle, and teardown controls. | Static Terraform checks do not prove deployed controls. | Part 3 gated workflow | `part3-managed-proof` |
| `performance_metric` | Future bounded throughput, latency, recovery, and cost measurements. | No Stage 4 local result is a performance claim. | Part 3 manual gate | `part3-managed-proof` |
| `evidence_integrity` | Commit, run, artifact, resource, label, limitation, and producer-version binding. | Integrity does not prove the underlying system is correct. | every PR and post-merge | `part3-managed-proof` |
