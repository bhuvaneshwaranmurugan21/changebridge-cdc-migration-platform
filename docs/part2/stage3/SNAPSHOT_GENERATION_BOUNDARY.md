# Stage 3 snapshot-generation boundary

Stage 3 materializes exactly the accepted snapshot at PostgreSQL LSN `0/194FB20` into one
generation-owned Iceberg namespace. Source authority is the Stage 1 pre-boundary oracle. Envelope
authority is the unchanged Stage 2 normalizer. Target authority is the Iceberg commit metadata plus
the file-backed SQLite generation registry.

The admitted input is six `orders` rows and 66 `order_items` rows. The handoff also carries one
transparently synthetic post-`S` CDC record to demonstrate separation; that record is preserved for
Stage 4 and never submitted to the snapshot loader.

The stage ends in `CDC_APPLYING`, not `ACTIVE` or `PUBLISHED`. It does not apply CDC, evolve a
schema, publish a consumer pointer, or establish any managed-service property.
