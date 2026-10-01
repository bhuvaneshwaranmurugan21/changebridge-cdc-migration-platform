# Part 3 completion contract

Part 3 is the final ChangeBridge part. It starts only from `PART2_COMPLETION_VERIFIED` at commit
`fd93d0863114ac131b79c011b2205a233fe185d7`, tree
`5be57fe4dc8369e7324770accb662e3cca9c8883`. Part 1 and Part 2 evidence is immutable.

The eight ordered stages are managed authority, deployable platform, AWS admission, managed happy
path, managed recovery, cutover and rollback, operational closure, and project completion. A later
stage cannot substitute for an earlier checkpoint. Local proof cannot be relabelled as managed
proof, and documentation cannot substitute for execution evidence.

Effective requirement authority is the immutable Part 2 completion registry plus
`requirements/part3-stage1-requirement-corrections.json`. The overlay corrects stale local status
projections without rewriting files hashed by the accepted Part 2 artifact chain.

AWS mutation is prohibited while the ChangeBridge account, region, budget, identity and OIDC
bindings are `UNASSIGNED`. Final completion requires all eight checkpoints, authoritative managed
receipts bound to exact revisions and resources, lifecycle closure, truthful claims, and the
external checkpoint `PROJECT_COMPLETION_VERIFIED`.
