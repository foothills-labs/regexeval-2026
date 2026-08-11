"""Paths and run constants. No machine-specific values anywhere in here.

Every path is derived from the repo root or overridable by environment
variable, so a clone runs the same way on any machine.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The corpus is not redistributed -- `make setup` downloads it here.
DATA_DIR = Path(os.environ.get("REGEXLB_DATA", REPO / "data"))
REGEXEVAL_PATH = Path(os.environ.get("REGEXEVAL_PATH", DATA_DIR / "RegexEval.json"))
REGEXEVAL_URL = (
    "https://raw.githubusercontent.com/s2e-lab/RegexEval/master"
    "/DatasetCollection/RegexEval.json"
)

PREDICTIONS_DIR = REPO / "predictions"
RESULTS_DIR = REPO / "results"

# The scoring engine is pinned by commit: 0.4.0 is not on PyPI, so a
# version specifier does not resolve to it.
REGEXBENCH_COMMIT = "05d7547b1a71e6dd5cb00d71bf4dac7732be3ecd"
REGEXBENCH_VERSION = "0.4.0"

# Sampling, recorded with every result.
TEMPERATURE = 0.0
MAX_TOKENS = 200


def require_dataset() -> Path:
    if not REGEXEVAL_PATH.exists():
        raise SystemExit(
            f"Corpus not found at {REGEXEVAL_PATH}\n"
            f"Run:  make setup     (downloads it from {REGEXEVAL_URL})"
        )
    return REGEXEVAL_PATH
