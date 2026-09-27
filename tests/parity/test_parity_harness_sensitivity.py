"""Harness self-check: proof the parity gate has teeth.

Each test injects one small, local, temporary semantic perturbation with
pytest's `monkeypatch` (never by editing production files), replays one
golden case, and asserts the comparison FAILS and pinpoints the drift. A
control test asserts the same replay is clean without the perturbation, so
every failure below is attributable to its perturbation alone.

Kept as permanent regression tests: later groups will adapt the harness
(stage names, node boundaries) while refactoring the evaluator, and these
guard against the harness silently losing sensitivity in the process.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

import strategy_engine.indicators.implementations.range_evaluator as range_evaluator
import strategy_engine.strategies.application.evaluate_range_batch as evaluate_range_batch
import strategy_engine.strategies.ema_pullback.evaluator as evaluator_module
import strategy_engine.strategies.ema_pullback.setups as setups
from parity.compare import Mismatch, compare_case, format_report
from parity.harness import GOLDEN_DIR, record_payload
from parity.snapshot import ArrayStore, read_json_gz
from strategy_engine.adapters.http import strategy_routes


def replay(
    case_name: str, golden_store: ArrayStore, *, memo_enabled: bool | None = None
) -> list[Mismatch]:
    golden = read_json_gz(GOLDEN_DIR / "cases" / f"{case_name}.json.gz")
    actual, actual_store = record_payload(
        case_name, golden["request_payload"], memo_enabled=memo_enabled
    )
    mismatches = compare_case(golden, actual, golden_store, actual_store)
    print(f"\n--- {case_name} ---\n{format_report(mismatches, limit=12)}")
    return mismatches


def variants_with_drift(mismatches: list[Mismatch], case_name: str) -> set[str]:
    prefix = f"{case_name}.variant["
    return {
        item.path[len(prefix) :].split("=", 1)[1].split(".", 1)[0]
        for item in mismatches
        if item.path.startswith(prefix)
    }


@pytest.fixture(scope="module")
def golden_store() -> ArrayStore:
    return ArrayStore.load(GOLDEN_DIR / "arrays.npz", verify=False)


def _wrap_ema(
    monkeypatch: pytest.MonkeyPatch, transform: Callable[[Callable[..., Any], Any, Any], Any]
) -> None:
    original = range_evaluator._ema_values

    def perturbed(frame: pd.DataFrame, feature: Any) -> Any:
        return transform(original, frame, feature)

    monkeypatch.setattr(range_evaluator, "_ema_values", perturbed)


def test_control_unperturbed_replays_clean(golden_store: ArrayStore) -> None:
    for case_name in (
        "probe_default_indicator_fields",
        "probe_default_setup_params",
        "synthetic_failures_mixed",
    ):
        assert replay(case_name, golden_store) == []


def test_detects_one_ulp_drift_in_one_indicator_value(
    monkeypatch: pytest.MonkeyPatch, golden_store: ArrayStore
) -> None:
    """Last bar of every EMA nudged by a single ulp: invisible to `==` on
    most downstream masks and to the NDJSON, visible to the bitwise rule."""

    def nudge_last(original: Callable[..., Any], frame: Any, feature: Any) -> Any:
        values = original(frame, feature).copy()
        values.iloc[-1] = np.nextafter(values.iloc[-1], np.inf)
        return values

    _wrap_ema(monkeypatch, nudge_last)
    mismatches = replay("probe_default_indicator_fields", golden_store)
    bitwise = [item for item in mismatches if item.rule == "float64-bitwise"]
    assert bitwise, "1-ulp EMA drift was not detected"
    assert any(item.path.endswith(".frame['series']['ema_close_base_200']") for item in bitwise)
    assert all(
        "1/12000 value(s) not bit-identical; first at bar 11999" in item.detail for item in bitwise
    )
    assert "ndjson-bytes" not in {item.rule for item in mismatches}


def test_detects_ema_reading_open_instead_of_close(
    monkeypatch: pytest.MonkeyPatch, golden_store: ArrayStore
) -> None:
    def swap_source(original: Callable[..., Any], frame: Any, feature: Any) -> Any:
        if feature.source == "close":
            feature = dataclasses.replace(feature, source="open")
        return original(frame, feature)

    _wrap_ema(monkeypatch, swap_source)
    # On this case the swap moves indicator values, direction/setup masks
    # and potential entries but not a single executed entry: the NDJSON is
    # byte-identical, so only the intermediate recording catches it.
    mismatches = replay("probe_default_indicator_fields", golden_store)
    rules = {item.rule for item in mismatches}
    assert {"float64-bitwise", "bool-exact", "None-positions"} <= rules
    assert "ndjson-bytes" not in rules
    assert any(".evaluation.direction_blockers[" in item.path for item in mismatches)
    assert any(".evaluation.potential_entries[" in item.path for item in mismatches)
    # On a real sweep the same drift also reaches executed entries / wire.
    mismatches = replay("real_untouched_only_sweep", golden_store)
    assert any(item.rule == "ndjson-bytes" for item in mismatches)
    assert any(".evaluation.entries[" in item.path for item in mismatches)


def test_detects_changed_default_parameter_only_where_default_applies(
    monkeypatch: pytest.MonkeyPatch, golden_store: ArrayStore
) -> None:
    """untouched_anchor_setup's lookback default 50 -> 51. Only variants that
    OMIT lookback may drift; the explicit-50 twin must stay clean.

    The perturbation changes the default inside the compute only, so it is
    replayed with the range-batch memo OFF: every node computes on its own,
    exactly the harness sensitivity this test pins. (With memo ON a
    compute-only default is a resolve/compute normalization desync -- see
    the next test.)"""

    original = setups._untouched_anchor

    def default_51(frame: Any, anchor_id: str, params: Any, side: str) -> Any:
        if "lookback" not in params:
            params = {**params, "lookback": 51}
        return original(frame, anchor_id, params, side)

    monkeypatch.setattr(setups, "_untouched_anchor", default_51)
    case_name = "probe_default_setup_params"
    mismatches = replay(case_name, golden_store, memo_enabled=False)
    assert variants_with_drift(mismatches, case_name) == {
        "untouched-lookback-omitted",
        "untouched-params-omitted",
    }
    assert any(
        item.path.endswith(".trace['untouched_prior']") and item.rule == "bool-exact"
        for item in mismatches
    )


_OMITTED_LOOKBACK = {"untouched-lookback-omitted", "untouched-params-omitted"}


def test_default_change_with_memo_on_drifts_only_where_default_applies(
    monkeypatch: pytest.MonkeyPatch, golden_store: ArrayStore
) -> None:
    """A real default change lives in the normalization helper shared by
    `compute()` and `resolve()` (design.md risk mitigation), so the memo
    identity follows it: with memo ON, still only the variants that omit
    lookback drift -- the explicit-50 twin is a distinct identity now."""

    original = setups._untouched_anchor_params

    def default_51(params: Any) -> tuple[int, int]:
        if "lookback" not in params:
            params = {**params, "lookback": 51}
        return original(params)

    monkeypatch.setattr(setups, "_untouched_anchor_params", default_51)
    case_name = "probe_default_setup_params"
    mismatches = replay(case_name, golden_store, memo_enabled=True)
    assert variants_with_drift(mismatches, case_name) == _OMITTED_LOOKBACK


def test_resolve_compute_default_desync_with_memo_on_is_detected(
    monkeypatch: pytest.MonkeyPatch, golden_store: ArrayStore
) -> None:
    """The design.md D2 risk itself: `compute()` applies a default that
    `resolve()` does not. The omitted and explicit-50 variants then share an
    identity although they compute differently, so memo ON serves the
    drifted result to the explicit twin as well. The parity gate catches it
    (on every variant sharing the identity), which is why no family is
    memoized without passing it."""

    original = setups._untouched_anchor

    def default_51(frame: Any, anchor_id: str, params: Any, side: str) -> Any:
        if "lookback" not in params:
            params = {**params, "lookback": 51}
        return original(frame, anchor_id, params, side)

    monkeypatch.setattr(setups, "_untouched_anchor", default_51)
    case_name = "probe_default_setup_params"
    mismatches = replay(case_name, golden_store, memo_enabled=True)
    drifted = variants_with_drift(mismatches, case_name)
    assert drifted > _OMITTED_LOOKBACK  # strict superset
    assert "untouched-lookback-50-explicit" in drifted


def test_detects_caught_failure_becoming_propagated(
    monkeypatch: pytest.MonkeyPatch, golden_store: ArrayStore
) -> None:
    """Per-variant catch boundary broken: the first failing variant now
    escapes the stream instead of producing an error line."""

    class NotAStrategyEngineError(Exception):
        pass

    monkeypatch.setattr(evaluate_range_batch, "StrategyEngineError", NotAStrategyEngineError)
    mismatches = replay("synthetic_failures_mixed", golden_store)
    paths = {item.path for item in mismatches}
    assert "synthetic_failures_mixed.ndjson.termination" in paths
    assert any(
        item.path.endswith("=fail-validate-unsupported-trigger.outcome.disposition")
        and "golden='caught' actual='propagated'" in item.detail
        for item in mismatches
    )


def test_detects_failure_message_drift(
    monkeypatch: pytest.MonkeyPatch, golden_store: ArrayStore
) -> None:
    original = setups._anchor_stack_width

    def reworded(*args: Any, **kwargs: Any) -> Any:
        try:
            return original(*args, **kwargs)
        except setups.InvalidRequestError as exc:
            raise setups.InvalidRequestError(exc.message + ".", **exc.details) from None

    monkeypatch.setattr(setups, "_anchor_stack_width", reworded)
    mismatches = replay("synthetic_failures_mixed", golden_store)
    assert any(
        item.path.endswith("=fail-setups-nonpositive-width.outcome.message") for item in mismatches
    )
    assert any(item.rule == "ndjson-bytes" for item in mismatches)


def test_detects_ndjson_only_serialization_drift(
    monkeypatch: pytest.MonkeyPatch, golden_store: ArrayStore
) -> None:
    """Identical computation, different wire bytes (key order)."""

    monkeypatch.setattr(
        strategy_routes,
        "json",
        SimpleNamespace(dumps=lambda value: json.dumps(value, sort_keys=True)),
    )
    mismatches = replay("probe_default_indicator_fields", golden_store)
    assert mismatches
    assert {item.rule for item in mismatches} == {"ndjson-bytes"}


def test_records_uncaught_projection_assertion_as_propagated(
    monkeypatch: pytest.MonkeyPatch, golden_store: ArrayStore
) -> None:
    """No valid spec in the corpus reaches the projection's AssertionError
    paths, so propagation is exercised by injection: the harness must see
    the stream terminate after the preceding line, with the exception
    category/message and 'propagated' disposition."""

    original = evaluator_module.build_historical_execution_projection
    calls = {"count": 0}

    def fail_second(**kwargs: Any) -> Any:
        calls["count"] += 1
        if calls["count"] == 2:
            raise AssertionError("injected projection invariant failure")
        return original(**kwargs)

    monkeypatch.setattr(evaluator_module, "build_historical_execution_projection", fail_second)
    golden = read_json_gz(GOLDEN_DIR / "cases" / "probe_default_indicator_fields.json.gz")
    actual, _ = record_payload("probe", golden["request_payload"])
    termination = actual["ndjson"]["termination"]
    assert termination["kind"] == "propagated"
    assert termination["after_lines"] == 1
    assert termination["category"] == "builtins.AssertionError"
    assert termination["message"] == "injected projection invariant failure"
    outcome = actual["candidates"][1]["outcome"]
    assert outcome["disposition"] == "propagated"
    assert outcome["stage"][-1] == "build_historical_execution_projection"
    assert len(actual["candidates"]) == 2
