"""(Re)record the golden parity baseline (task 1.6).

Only legitimate against the PRE-change evaluator: the golden is the
definition of "unchanged behaviour" for every later stage of
`batch-computation-reuse`. The manifest pins the source digest of
`src/strategy_engine` that produced it.

    PYTHONPATH=src:tests .venv/bin/python -m parity.record_golden

Layout written under tests/parity/golden/:
    manifest.json          provenance, environment, per-case index
    cases/<case>.json.gz   request payload, exact NDJSON lines, per-candidate
                           encoded plan/frame/evaluation/projection/outcome
    arrays.npz             content-addressed float64/bool/int arrays the case
                           files reference (deduplicated across all cases)
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from parity.corpus import all_cases
from parity.harness import (
    GOLDEN_DIR,
    MARKET_FIXTURE,
    market_fixture_bytes,
    market_fixture_meta,
    record_case,
)
from parity.snapshot import FORMAT_VERSION, ArrayStore, write_json_gz

_REPO_ROOT = Path(__file__).resolve().parents[2]


def source_digest() -> str:
    """sha256 over every production source file (path + bytes)."""

    digest = hashlib.sha256()
    source_root = _REPO_ROOT / "src" / "strategy_engine"
    for path in sorted(source_root.rglob("*.py")):
        digest.update(path.relative_to(_REPO_ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_head() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    cases_dir = GOLDEN_DIR / "cases"
    if cases_dir.exists():
        shutil.rmtree(cases_dir)
    cases_dir.mkdir(parents=True)
    store = ArrayStore()
    index: list[dict[str, Any]] = []
    started = time.time()
    for case in all_cases():
        record, case_store = record_case(case)
        record["format_version"] = FORMAT_VERSION
        store.update(case_store)
        target = cases_dir / f"{case.name}.json.gz"
        write_json_gz(target, record)
        index.append(
            {
                "case": case.name,
                "group": case.group,
                "variants": len(case.variants),
                "file": target.relative_to(GOLDEN_DIR).as_posix(),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
        print(f"recorded {case.name} ({len(case.variants)} variants)")
    arrays_path = GOLDEN_DIR / "arrays.npz"
    store.save(arrays_path)
    manifest = {
        "format_version": FORMAT_VERSION,
        "recorded_against": {
            "git_head": _git_head(),
            "src_strategy_engine_sha256": source_digest(),
            "note": "pre-change evaluator (batch-computation-reuse group 1 baseline)",
        },
        "environment": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "market_fixture": {
            "file": f"fixtures/{MARKET_FIXTURE}",
            "sha256": hashlib.sha256(market_fixture_bytes()).hexdigest(),
            **market_fixture_meta(),
        },
        "arrays": {
            "file": "arrays.npz",
            "count": len(store.arrays),
            "raw_bytes": int(sum(array.nbytes for array in store.arrays.values())),
            "sha256": hashlib.sha256(arrays_path.read_bytes()).hexdigest(),
        },
        "cases": index,
        "record_seconds": round(time.time() - started, 1),
    }
    (GOLDEN_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{len(index)} cases, {len(store.arrays)} arrays -> {GOLDEN_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
