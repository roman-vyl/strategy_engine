"""Declared-invariant regression gate (OpenSpec
`composite-setup-pre-entry-predicates-v1`, task 0.2).

For every parity-corpus case (none uses `composite_setup`) the public
result, plan, memoized node identities/compute counts and the indicator
contract must equal the baseline recorded on the pre-change code. See
`parity/invariants.py` for exactly what is (and is not) asserted and which
invariant each part protects.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from parity.corpus import all_cases
from parity.invariants import case_invariants, indicator_contract_invariants
from parity.record_invariants import BASELINE_PATH

_BASELINE: dict[str, Any] = json.loads(BASELINE_PATH.read_text())
_CASES = {case.name: case for case in all_cases()}


def test_baseline_covers_the_whole_corpus() -> None:
    assert sorted(_BASELINE["cases"]) == sorted(_CASES)


@pytest.mark.parametrize("name", sorted(_CASES))
def test_case_invariants_unchanged(name: str) -> None:
    actual = json.loads(json.dumps(case_invariants(_CASES[name]), sort_keys=True))
    expected = _BASELINE["cases"][name]
    assert actual["public"] == expected["public"], "public /range-batch result changed"
    assert actual["plan"] == expected["plan"], "plan_hash / plan labels changed"
    assert actual["nodes"]["per_family"] == expected["nodes"]["per_family"], (
        "memoized compute counts per node family changed"
    )
    assert actual["nodes"]["identities"] == expected["nodes"]["identities"], (
        "memoized node identities changed"
    )


def test_indicator_contract_unchanged() -> None:
    actual = json.loads(json.dumps(indicator_contract_invariants(), sort_keys=True))
    assert actual == _BASELINE["indicator_contract"]
