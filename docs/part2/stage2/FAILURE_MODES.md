# Stage 2 failure modes

- Manifest identity, path, checksum, size, row-count, sequence, generation, or boundary mismatch:
  abort before canonical output.
- Unknown profile, field, operation, contract, or schema: deterministic quarantine or manifest
  rejection under the closed reason registry.
- Missing source transaction/order metadata or full before image: quarantine; never synthesize.
- Malformed, nonadvancing, or beyond-end LSN: quarantine.
- Identical event identity and payload: duplicate-safe. Same identity with a different payload:
  terminal conflict and quarantine.
- Interrupted output: temporary directory is removed and no successful sealed output exists.
- Any predecessor evidence drift: stop the stage and restore isolation; never update protected
  evidence to make validation pass.
