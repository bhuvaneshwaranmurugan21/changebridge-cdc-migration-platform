# Threat model

| Threat | Design control | Remaining managed proof |
|---|---|---|
| Public migration data | S3 public-access block | Config/policy evidence |
| Data read outside intended role | KMS encryption and scoped DMS role | Access Analyzer review |
| CDC payload tampering | Canonical transaction and manifest digests | Immutable object/version proof |
| Stale concurrent cutover | Conditional active-pointer update | DynamoDB conditional-failure trace |
| Destructive schema drift | Compatibility gate and quarantine | Real DDL injection test |
| Evidence disclosure | Redacted identifiers and synthetic data | Bundle review before commit |

The lab handles synthetic data only and makes no compliance certification claim.

