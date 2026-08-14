# Workload and capacity model

The bounded AWS lab migrates one synthetic PostgreSQL schema and a controlled CDC interval. It
records source rows, change events, bytes, transaction sizes, DMS source/target latency, Spark
runtime, reconciliation time, and end-to-end recovery time. Static service limits are design
inputs, never substituted for measured throughput.

Production sizing starts with peak change bytes/s and transaction distribution, not average row
count. A single very large transaction can dominate apply latency even when average CDC volume is
small. Retention must exceed the maximum credible outage plus replay and validation time.

The repository deliberately does not claim zero downtime, a specific RPO/RTO, or production
scale until a workload trace and managed evidence bundle exist.

