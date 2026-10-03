# Stage 3 failure modes

- Account or region mismatch: stop before any mutation.
- OIDC provider absent or trust broader than the exact repository boundary: stop and correct the
  proposal; do not fall back to long-lived credentials.
- Candidate name already exists: record the collision and stop; do not import or overwrite it.
- Budget or alerts cannot be observed: retain the mutation block.
- Alert endpoint cannot be kept outside public artifacts: retain the mutation block.
- Required service or quota is unavailable: reduce or redesign the bounded experiment; do not
  weaken acceptance criteria.
- Cost estimate exceeds the USD 20 shared monthly guardrail: do not authorize the bootstrap.
- Bootstrap API acknowledgement is ambiguous: reconcile with read-only APIs before retrying.
- Partial bootstrap: inventory successful writes, stop, and use the approved recovery path.
- Approaching the 48-hour deadline: stop new work and execute the separately authorized teardown.
