#!/usr/bin/env python3
"""Copy the audited BBB strategy source slice without modifying its contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

PRIMARY = Path("research/strategies/ema_pullback")
TESTS = (
    "tests/ema_pullback_context_helpers.py",
    "tests/phase_rule_test_helpers.py",
    "tests/test_anchor_stack_width_setup.py",
    "tests/test_consumer_roles.py",
    "tests/test_ema_pullback_components.py",
    "tests/test_ema_pullback_exit_ema_signals.py",
    "tests/test_ema_pullback_exits.py",
    "tests/test_ema_pullback_feature_profile.py",
    "tests/test_ema_pullback_features_atr.py",
    "tests/test_ema_pullback_pipeline.py",
    "tests/test_ema_pullback_setup_stack.py",
    "tests/test_exit_attribution.py",
    "tests/test_exit_management_contracts.py",
    "tests/test_htf_regime_gate.py",
    "tests/test_managed_exit_provider.py",
    "tests/test_managed_runtime_exit_components.py",
    "tests/test_managed_stop_components.py",
    "tests/test_managed_take_components.py",
    "tests/test_phase_rule_conditions.py",
    "tests/test_runtime_reusable_signal_exits.py",
    "tests/test_setup_component_context_boundary.py",
    "tests/test_strategy_level_contexts.py",
    "tests/test_trend_strength_episode_blocker.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bbb_root", type=Path)
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_root = args.bbb_root.resolve()
    target_root = args.target.resolve()
    primary = source_root / PRIMARY
    if not primary.is_dir():
        raise SystemExit(f"missing audited strategy directory: {primary}")

    files = sorted(path for path in primary.rglob("*") if path.is_file())
    if len(files) != 61:
        raise SystemExit(f"expected 61 strategy files from audited snapshot, found {len(files)}")
    for relative in TESTS:
        path = source_root / relative
        if not path.is_file():
            raise SystemExit(f"missing audited test file: {path}")
        files.append(path)

    manifest: list[dict[str, str]] = []
    for source in files:
        relative = source.relative_to(source_root)
        destination = target_root / "legacy_source" / "bbb" / relative
        manifest.append(
            {
                "source": relative.as_posix(),
                "destination": destination.relative_to(target_root).as_posix(),
                "sha256": sha256(source),
            }
        )
        print(f"COPY {relative} -> {destination.relative_to(target_root)}")
        if not args.dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    if args.dry_run:
        print(f"DRY RUN PASS: {len(manifest)} files; no files changed")
        return

    manifest_path = target_root / "legacy_source" / "bbb" / "copy_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Installed {len(manifest)} files. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
