"""Unit tests for the parity comparison rules (task 1.5)."""

from __future__ import annotations

from typing import Any

import numpy as np

from parity.compare import (
    compare_bool_exact,
    compare_encoded,
    compare_failure,
    compare_float64_bitwise,
    compare_research_artifacts_semantic,
)
from parity.harness import _exception_record
from parity.snapshot import ArrayStore, encode
from strategy_engine.domain.errors import InvalidRequestError


def _diff(golden: Any, actual: Any) -> list[str]:
    golden_store, actual_store = ArrayStore(), ArrayStore()
    return [
        item.rule
        for item in compare_encoded(
            "x",
            encode(golden, golden_store),
            encode(actual, actual_store),
            golden_store,
            actual_store,
        )
    ]


def test_float_rule_is_bitwise_not_equality() -> None:
    assert compare_float64_bitwise("x", np.array([0.0]), np.array([-0.0]))  # 0.0 == -0.0
    one_ulp = np.nextafter(1.0, 2.0)
    assert compare_float64_bitwise("x", np.array([1.0]), np.array([one_ulp]))
    nan_a = np.frombuffer(np.uint64(0x7FF8000000000000).tobytes(), dtype=np.float64)
    nan_b = np.frombuffer(np.uint64(0x7FF8000000000001).tobytes(), dtype=np.float64)
    assert compare_float64_bitwise("x", nan_a, nan_b)  # NaN payloads differ
    assert not compare_float64_bitwise("x", np.array([1.0, np.nan]), np.array([1.0, np.nan]))
    assert _diff((1.0, 2.0), [1.0, 2.0]) == []  # container type is not semantic
    assert _diff(0.1 + 0.2, 0.3) == ["float64-bitwise"]


def test_none_and_nan_positions_are_distinct_and_exact() -> None:
    assert _diff((1.0, None), (1.0, float("nan"))) == ["None-positions"]
    assert _diff((1.0, float("nan"), 2.0), (1.0, 2.0, float("nan"))) == ["NaN-positions"]
    assert _diff((None, 1.0), (None, 1.0)) == []


def test_bool_and_structure_rules_are_exact() -> None:
    assert compare_bool_exact("x", np.array([True, False]), np.array([True, True]))
    assert _diff((True, False), (True, False)) == []
    assert _diff((1, 2), (1.0, 2.0)) == ["structure"]  # int vs float kind
    assert _diff({"a": 1, "b": 2}, {"b": 2, "a": 1}) == ["structure"]  # order observable
    assert _diff(("up", "down"), ("up", "neutral")) == ["str-exact"]


def test_failure_rule_uses_observable_fields_not_exception_identity() -> None:
    def record(exc: BaseException, disposition: str) -> dict[str, Any]:
        return {
            **_exception_record(exc),
            "disposition": disposition,
            "variant_index": 2,
            "variant_id": "v",
            "stage": ["execute_projection", "evaluate_setups"],
        }

    first = InvalidRequestError("boom", field="x")
    second = InvalidRequestError("boom", field="x")  # different object, no traceback
    assert first is not second
    assert compare_failure("f", record(first, "caught"), record(second, "caught")) == []
    assert compare_failure("f", record(first, "caught"), record(second, "propagated"))
    assert compare_failure(
        "f", record(first, "caught"), record(InvalidRequestError("boom", field="y"), "caught")
    )
    assert compare_failure("f", record(first, "caught"), record(AssertionError("boom"), "caught"))
    moved = {**record(second, "caught"), "stage": ["execute_projection", "evaluate_triggers"]}
    assert compare_failure("f", record(first, "caught"), moved)


def test_research_artifact_rule_excludes_only_non_deterministic_metadata() -> None:
    golden = {"run_id": "run_a", "created_at_utc": "t1", "metrics": {"net_pnl": "1.5"}}
    same = {"run_id": "run_b", "created_at_utc": "t2", "metrics": {"net_pnl": "1.5"}}
    drifted = {"run_id": "run_b", "created_at_utc": "t2", "metrics": {"net_pnl": "1.50"}}
    assert compare_research_artifacts_semantic(golden, same) == []
    assert compare_research_artifacts_semantic(golden, drifted)
