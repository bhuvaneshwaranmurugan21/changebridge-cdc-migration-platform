#!/usr/bin/env python3
"""Bounded Stage 7 publication laboratory entry point."""

import importlib
import sys
from pathlib import Path


def main() -> None:
    """Run the repository script when invoked by file path or module path."""

    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    runner = importlib.import_module("scripts.run_stage27_publication_lab")
    runner.main()

if __name__ == "__main__":
    main()
