#!/usr/bin/env python3
"""Run the complete BBB-to-Strategy-Engine semantic parity acceptance gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "parity/ema_pullback_semantic_parity_manifest.json"
DEFAULT_REPORT = ROOT / "artifacts/ema_pullback_semantic_parity_report.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_provenance(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        normalized = list(payload)
    else:
        entries = payload.get("files") or payload.get("entries") or []
        if isinstance(entries, dict):
            normalized = [{"path": key, "sha256": value} for key, value in entries.items()]
        else:
            normalized = list(entries)
    failures: list[str] = []
    checked = 0
    for item in normalized:
        relative = item.get("destination") or item.get("path") or item.get("source")
        expected = item.get("sha256")
        if not relative or not expected:
            continue
        candidate = ROOT / relative
        if not candidate.exists():
            candidate = ROOT / "legacy_source/bbb" / relative
        if not candidate.exists():
            failures.append(f"missing:{relative}")
            continue
        checked += 1
        actual = sha256(candidate)
        if actual != expected:
            failures.append(f"hash_mismatch:{relative}")
    return {"checked": checked, "failures": failures, "passed": not failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-pytest", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    tests: list[str] = []
    stages: list[dict[str, Any]] = []
    for stage in manifest["required_stages"]:
        stage_tests = list(stage["tests"])
        missing = [test for test in stage_tests if not (ROOT / test).is_file()]
        stages.append({"stage": stage["stage"], "tests": stage_tests, "missing": missing})
        tests.extend(stage_tests)

    provenance_path = ROOT / manifest["source_provenance"]
    provenance = verify_source_provenance(provenance_path)
    pytest_returncode: int | None = None
    if not args.no_pytest and not any(stage["missing"] for stage in stages):
        command = [sys.executable, "-m", "pytest", "-q", *tests]
        pytest_returncode = subprocess.run(command, cwd=ROOT, check=False).returncode

    passed = (
        provenance["passed"]
        and not any(stage["missing"] for stage in stages)
        and (args.no_pytest or pytest_returncode == 0)
    )
    report = {
        "report_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy_id": manifest["strategy_id"],
        "compatibility_profile": manifest["compatibility_profile"],
        "manifest_sha256": sha256(args.manifest),
        "source_manifest_sha256": sha256(provenance_path),
        "source_provenance": provenance,
        "stages": stages,
        "pytest_returncode": pytest_returncode,
        "passed": passed,
        "explicitly_out_of_scope": manifest["explicitly_out_of_scope"],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
