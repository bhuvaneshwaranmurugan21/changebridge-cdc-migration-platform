# Managed-proof authority

Part 3 Stage 1 is repository-only authority work. It performs no AWS call, infrastructure change,
runtime change, deployment, managed experiment, or performance test.

The accepted Part 2 result is `LOCAL_VERIFIED`. Managed claims require a future exact-run chain
from immutable source inputs through named AWS resources, configuration revisions, execution
receipts, reconciliation output, recovery evidence, cost records, and lifecycle closure. Until
the ChangeBridge account and region are assigned, AWS mutation is blocked.

Current-tree validators prove the final accepted repository. Historical validators whose original
authority files were legitimately superseded are evaluated at their accepted commit; frozen
preservation validators and evidence digests prove that their accepted evidence did not change.

The Part 2 Stage 7 manifest owns the legacy completion-requirement projection. Stage 1 therefore
records the 17 stale local-status corrections in a validated overlay instead of mutating that
predecessor-owned projection. Consumers compute effective status from the base registry followed
by the overlay; managed and measured requirements are not promoted.
