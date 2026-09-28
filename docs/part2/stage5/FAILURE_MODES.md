# Stage 5 failure modes

| Failure | Stable diagnostic | Required outcome |
|---|---|---|
| Unknown contract identity | `CB25S001_UNKNOWN_CONTRACT` | Quarantine before mutation |
| Policy digest mismatch | `CB25S010_POLICY_MISMATCH` | Quarantine before mutation |
| Primary-key definition changed | `CB25S020_PRIMARY_KEY_CHANGED` | Quarantine and reject generation |
| Field removed | `CB25S021_FIELD_REMOVED` | Quarantine and reject generation |
| Type changed | `CB25S022_TYPE_CHANGED` | Quarantine and reject generation |
| Nullability narrowed | `CB25S023_NULLABILITY_NARROWED` | Quarantine and reject generation |
| Required field added | `CB25S024_REQUIRED_FIELD_ADDED` | Quarantine and reject generation |
| Primary-key value updated | `CB25S031_PRIMARY_KEY_VALUE_CHANGED` | Reject event before CDC mutation |
| Missing exact receipt | `CB25C006_ADMISSION_REQUIRED` | Block CDC assembly |
| Open generation quarantine | `CB25C005_GENERATION_QUARANTINED` | Block CDC assembly |
| Rejected generation | `CB25C009_GENERATION_REJECTED` | Block CDC assembly |
| Conflicting Iceberg apply token | `CB25I004_APPLY_TOKEN_CONFLICT` | Stop; no overwrite |

Every outcome preserves frontier `0/194FE20`. Unknown changes are not silently promoted;
re-adjudication requires a new registered contract or policy authority and a reviewable run.
