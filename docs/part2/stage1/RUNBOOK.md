# Stage 1 Reproduction Runbook

## Fast authority lane

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
ruff check src scripts tests
mypy src scripts/stage21_postgres_adapter.py scripts/run_stage21_postgres_lab.py
pytest
python scripts/validate_part1_frozen.py
python scripts/validate_part2_stage1.py
```

The ordinary test command intentionally skips the PostgreSQL-marked test when the required
environment flag and real service are absent. That skip is not Stage 1 completion evidence.

## Required PostgreSQL lane

The required lane is `.github/workflows/part2-stage1-postgres.yml`. It uses only the image recorded
in `evidence/part2/stage1/container-image-lock.json`, enables `wal_level=logical`, runs the
replication compatibility probe, and executes:

```bash
pytest -m postgres_integration tests/integration --no-cov
```

The lane fails if the service, exported snapshot, logical output plugin, integration test, cleanup,
or artifact upload fails. A skipped integration test is not accepted.

## Evidence regeneration

Download the exact workflow artifact identified by
`evidence/part2/stage1/boundary-capture-report.json`, extract `stage21-postgres-lab.json` outside the
repository, and run:

```bash
python scripts/build_stage21_evidence.py \
  --runtime-report /path/outside/repository/stage21-postgres-lab.json
python scripts/validate_part2_stage1.py
```

The raw report is intentionally not committed because it repeats complete row payloads and
run-specific material. The repository retains bounded summaries plus both the archive and raw JSON
SHA-256 digests.

## Cleanup verification

Every laboratory run drops its persistent logical slot in a `finally` path and reports
`slot_dropped=true`. Source schemas are isolated per run and dropped after the report is built. The
GitHub service container is destroyed by the hosted runner after the job. No ambient PostgreSQL,
AWS resource, or shared database is touched.
