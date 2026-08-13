# AWS reference infrastructure

This module defines encrypted/versioned landing and evidence buckets, generation and active
pointer ledgers, a Glue candidate database, DMS transaction-preserving S3 target, optional DMS
full-load-and-CDC task, and a lag alarm.

`terraform validate` proves configuration shape only. It does not prove permissions, quotas,
source WAL configuration, end-to-end DMS behavior, Iceberg commits, scale, cost, or recovery.
Follow `docs/runbook.md` and attach the required evidence before changing the claim registry.

```bash
terraform init
terraform plan -var='source_endpoint_arn=...' -var='replication_instance_arn=...'
```
