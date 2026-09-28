# Stage 5 schema and key policy

## Authority boundary

Stage 5 consumes `PART2_STAGE4_CDC_APPLY_VERIFIED` at commit
`cbf575315e3b9bea3c0ee79f78e3288c8746effb`, tree
`30e26dd3d7cd89601de92bc6ec99ec0e1a2737f0`. It preserves the accepted generation, data,
transaction semantics, and checkpoint `0/194FE20`.

## Admission protocol

1. Resolve both exact contract identities from the registry.
2. Compare ordered typed primary-key definitions.
3. Evaluate the immutable policy and persist the deterministic decision.
4. For compatible change, atomically commit the Iceberg field plus recovery properties.
5. Persist a receipt binding the decision, policy, candidate digest, schema ID, metadata location,
   and apply token.
6. Admit CDC only when the event digest, compatible decision, and exact receipt all agree.

The supported proof case is `orders_source_contract/1.0.0` to `1.1.0`: add nullable, non-key
`source_note`. Existing six rows remain logically unchanged and read `null` for the new field.

## Fail-closed outcomes

| Change | Verdict | Before target mutation | Generation outcome |
|---|---|---|---|
| Exact replay | Compatible | Durable decision | Remains `CDC_APPLYING` |
| Nullable non-key addition | Compatible | Durable decision | Remains `CDC_APPLYING` |
| Unknown identity or policy | Unknown | Open quarantine | Admission blocked |
| Removal/type/narrowing/required add | Incompatible | Open quarantine | `REJECTED` |
| Primary-key definition change | Incompatible | Open quarantine and rejection record | `REJECTED` |
| Primary-key value update | Rejected event | Exact receipt required | No CDC mutation |

No rule infers defaults or coerces types. A rename is represented as remove-plus-add and therefore
fails closed.

## Claim boundary

The proof is local and bounded. It establishes neither AWS catalog behavior nor arbitrary schema
evolution, managed recovery, performance, publication, zero downtime, exactly-once delivery, or
production readiness. The candidate stays unpublished and unsealed.
