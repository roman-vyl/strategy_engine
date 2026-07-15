from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "parity/ema_pullback_semantic_parity_manifest.json"


def test_parity_manifest_covers_every_ported_semantic_stage() -> None:
    payload = json.loads(MANIFEST.read_text())
    stages = {item["stage"] for item in payload["required_stages"]}
    assert stages == {
        "feature_plan",
        "indicators",
        "contexts",
        "direction_blockers",
        "setups",
        "triggers",
        "exit_policy",
        "managed_policy",
        "public_api_contract",
    }


def test_all_manifest_tests_exist_and_are_unique() -> None:
    payload = json.loads(MANIFEST.read_text())
    tests = [test for stage in payload["required_stages"] for test in stage["tests"]]
    assert len(tests) == len(set(tests))
    assert all((ROOT / test).is_file() for test in tests)


def test_execution_and_bbb_cutover_are_not_misrepresented_as_semantic_parity() -> None:
    payload = json.loads(MANIFEST.read_text())
    out_of_scope = "\n".join(payload["explicitly_out_of_scope"])
    assert "fill arbitration" in out_of_scope
    assert "Workbench DTO" in out_of_scope
    assert "checkpointing" in out_of_scope
