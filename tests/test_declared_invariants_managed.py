"""Declared-invariant regression gate for managed specs (OpenSpec
`composite-managed-phase-condition-v1`, task 0.2).

Every case uses atomic phase rules only (no `composite_phase_condition`).
The `/range-batch` result (with its serialized managed projection -- design
D6), plan and memoized nodes (D8, D9), `/managed-replay` responses and live
open-trade results (D5, D7) must equal the baseline recorded on `main`
7b088ae -- the `batch-computation-reuse` requirement "No compute regression
for existing managed specs". See `parity/managed_invariants.py`.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from parity.managed_invariants import managed_case_invariants, managed_cases
from parity.record_invariants import MANAGED_BASELINE_PATH

_BASELINE: dict[str, Any] = json.loads(MANAGED_BASELINE_PATH.read_text())
_CASES = {case.name: case for case in managed_cases()}


def test_baseline_covers_the_managed_corpus() -> None:
    assert sorted(_BASELINE["cases"]) == sorted(_CASES)


@pytest.mark.parametrize("name", sorted(_CASES))
def test_managed_case_invariants_unchanged(name: str) -> None:
    actual = json.loads(json.dumps(managed_case_invariants(_CASES[name]), sort_keys=True))
    expected = _BASELINE["cases"][name]
    batch, expected_batch = actual["batch"], expected["batch"]
    assert batch["public"] == expected_batch["public"], (
        "public /range-batch result (incl. managed projection) changed"
    )
    assert batch["plan"] == expected_batch["plan"], "plan_hash / plan labels changed"
    assert batch["nodes"]["per_family"] == expected_batch["nodes"]["per_family"], (
        "memoized compute counts per node family changed"
    )
    assert batch["nodes"]["identities"] == expected_batch["nodes"]["identities"], (
        "memoized node identities changed"
    )
    assert actual["replay"] == expected["replay"], "/managed-replay response changed"
    assert actual["open_trade"] == expected["open_trade"], "live open-trade result changed"
