#!/usr/bin/env python3
"""Verify that the immutable BBB source copy matches its hash manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "legacy_source" / "bbb" / "copy_manifest.json"
    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for record in records:
        destination = root / record["destination"]
        if not destination.is_file():
            failures.append(f"missing: {record['destination']}")
            continue
        actual = sha256(destination)
        if actual != record["sha256"]:
            failures.append(
                f"hash mismatch: {record['destination']} expected={record['sha256']} actual={actual}"
            )
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"legacy source verification: PASS ({len(records)} files)")


if __name__ == "__main__":
    main()
