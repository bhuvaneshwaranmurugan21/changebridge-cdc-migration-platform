import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.postgres_integration
def test_stage26_postgres_observer(tmp_path: Path) -> None:
    dsn = os.getenv("CB_STAGE26_POSTGRES_DSN")
    if not dsn:
        pytest.skip("requires digest-pinned PostgreSQL service")
    output = tmp_path / "source.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/run_stage26_postgres_observer.py",
            "--dsn",
            dsn,
            "--output",
            str(output),
        ],
        check=True,
    )
    assert '"result": "PASS"' in output.read_text(encoding="utf-8")
