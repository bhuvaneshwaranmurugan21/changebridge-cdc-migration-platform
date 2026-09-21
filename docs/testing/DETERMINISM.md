# Determinism Standard

Stage 4 property tests use Hypothesis 6.168.0 with a derandomized, database-free profile; failures retain
their minimal counterexample. Fixtures record stable seeds. Pure tests use fixed UTC timestamps and no
ambient clock. Locale is fixed, unordered inputs are sorted, JSON is canonicalized, and absolute or
temporary paths are forbidden from evidence.

Validation records Python plus direct and transitive dependency versions. Concurrency is represented by
enumerated schedules, not wall-clock races. Generated views, validator output, simulator output, and
artifact digests are compared across two clean runs. Missing seed, version, schedule, or producer
metadata fails closed.

Repeatability proves only that the bounded local inputs produce identical outputs in the recorded
environment. It does not prove cross-platform equivalence or managed-runtime determinism.
