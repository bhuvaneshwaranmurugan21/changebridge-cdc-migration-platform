# Stage 2 local runbook

From a clean environment with the repository development extra installed:

```bash
python scripts/build_stage22_fixtures.py
changebridge normalize \
  --manifest tests/fixtures/part2-stage2/valid/manifest.json \
  --output /tmp/changebridge-stage22-output
python scripts/build_stage22_evidence.py
python scripts/validate_part2_stage2.py
ruff check .
mypy src/changebridge
pytest
```

Do not reuse an output directory. A nonzero normalization exit means the manifest failed or at
least one record was quarantined. Preserve the diagnostic and correct the source/profile contract;
do not relabel or bypass it.
