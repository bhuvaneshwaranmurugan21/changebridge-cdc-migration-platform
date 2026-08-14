# Interview defense

## Two-minute explanation

A DMS task can be healthy while the target is incomplete. ChangeBridge binds a snapshot frontier,
the contiguous CDC interval after it, immutable candidate data, reconciliation at the same
frontier, and a compare-and-swap cutover into one migration generation. A failed generation never
becomes consumer-visible, and rollback is a pointer change to a retained proof—not reverse DML.

## Questions to expect

1. **Where is the snapshot/CDC boundary?** The source snapshot LSN is persisted and the first CDC
   interval must start exactly there.
2. **How is replay safe?** The same transaction ID is accepted only with the same canonical digest.
3. **Why counts and digests?** Counts miss compensating corruption; canonical row digests expose it.
4. **How does schema change behave?** Additive compatible changes can proceed; destructive changes
   quarantine the generation pending a versioned contract.
5. **How do you cut over and roll back?** Conditional pointer publication prevents lost updates;
   rollback selects a retained proven generation.
6. **What ran on AWS?** Only a bundle passing `validate_aws_lab_evidence` supports an AWS-lab claim.

