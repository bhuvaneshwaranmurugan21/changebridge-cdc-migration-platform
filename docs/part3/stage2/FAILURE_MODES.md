# Stage 2 failure modes

- Entry commit, tree, or checkpoint mismatch: stop before editing.
- Protected evidence digest mismatch: report the exact path; never regenerate predecessor proof.
- Account, region, deployment ID, artifact identity, cost owner, or expiry unassigned: deployment
  remains blocked by Terraform preconditions.
- Runtime archive differs across identical builds: reject packaging and normalize its metadata.
- Iceberg checksum or Spark matrix differs: reject the artifact lock.
- Processing role can update the active pointer: reject the IAM boundary.
- Proof gate has a publication default: reject the state machine.
- Terraform validation attempts credential discovery or AWS refresh: terminate and correct the
  validation lane.
- New provider, dependency, or image required: stop for exact-version authorization.
- Terraform validates but AWS behavior is unknown: retain `LOCAL_VERIFIED`; proceed to Stage 3.
