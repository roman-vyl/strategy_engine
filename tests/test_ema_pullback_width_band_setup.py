"""anchor_stack_width_band_setup (OpenSpec `anchor-stack-width-band-setup-v1`):
parameter validation, inclusive band semantics, width equivalence with
`anchor_stack_width_setup`, composite child reuse, identity/memo and live
history."""

from __future__ import annotations

import copy
import math
from collections import Counter
from decimal import Decimal
from typing import Any

import pytest
from parity.corpus import _untouched, _variant, _width, base_spec
from parity.harness import Recorder, _drain_route, batch_payload, recording_services
from parity.invariants import _capturing_contexts

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import (
    EmaPullbackLiveCalculationRequirements,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import parse_width_band_params
from strategy_engine.strategies.ema_pullback.setups import _anchor_stack_width_band
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)

Spec = dict[str, Any]
BAND = "anchor_stack_width_band_setup"
NODE_WIDTH = "setup.anchor_stack_width_band.width"


def _band(instance_id: str = "band", **params: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {"atr_period": 48, "min_width_atr": 5.0}
    merged.update(params)
    return {"component_id": BAND, "instance_id": instance_id, "params": merged}


def _spec_with_setups(*setups: dict[str, Any]) -> Spec:
    spec = base_spec()
    spec["setups"] = list(setups)
    return spec


def _frame(width: tuple[float | None, ...]) -> FeatureFrame:
    """`width_atr[i] == width[i]` with fast=width, slow=0, atr=1 (None = NaN atr)."""

    n = len(width)
    time_ms = tuple(index * 300_000 for index in range(n))
    bars = tuple(
        MarketBar(t, Decimal(10), Decimal(10), Decimal(10), Decimal(10), Decimal(1))
        for t in time_ms
    )
    series: dict[str, tuple[str | None, ...]] = {
        "fast": tuple("0" if w is None else str(w) for w in width),
        "slow": ("0",) * n,
        "atr": tuple(None if w is None else "1" for w in width),
    }
    return FeatureFrame(
        market=MarketStream("BTCUSDT.P", "5m"),
        requested_range=TimeRange(0, n * 300_000),
        time_ms=time_ms,
        series=series,
        validity={},
        plan_hash="plan",
        market_data_hash="market",
        market_bars=bars,
    )


COLUMNS = {"fast": "fast", "slow": "slow", "atr": "atr"}


def _mask(width: tuple[float | None, ...], **params: Any) -> tuple[bool, ...]:
    mask, _ = _anchor_stack_width_band(_frame(width), COLUMNS, params)
    return mask


# -- parameters ---------------------------------------------------------------


def test_parameter_defaults() -> None:
    band = parse_width_band_params({"min_width_atr": 5})
    assert (band.min_width_atr, band.max_width_atr) == (5.0, None)
    assert (band.atr_timeframe, band.atr_period) == ("base", 14)


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"min_width_atr": 0},
        {"min_width_atr": -1},
        {"min_width_atr": True},
        {"min_width_atr": "5"},
        {"min_width_atr": float("nan")},
        {"min_width_atr": float("inf")},
        {"min_width_atr": 5, "max_width_atr": 4},
        {"min_width_atr": 5, "max_width_atr": None},
        {"min_width_atr": 5, "max_width_atr": float("inf")},
        {"min_width_atr": 5, "atr_period": 0},
        {"min_width_atr": 5, "atr_period": True},
        {"min_width_atr": 5, "atr_timeframe": ""},
        {"min_width_atr": 5, "width_lookback_bars": 80},
    ],
)
def test_invalid_params_are_rejected_statically(params: dict[str, Any]) -> None:
    item = {"component_id": BAND, "instance_id": "b", "params": params}
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_spec_with_setups(item))
    composite = {
        "component_id": "composite_setup",
        "instance_id": "combo",
        "params": {
            "children": [{"child_id": "b", "setup": {"component_id": BAND, "params": params}}],
            "paths": [{"path_id": "p", "require": ["b"]}],
        },
    }
    with pytest.raises(InvalidRequestError):
        check_ema_pullback_static_semantics(_spec_with_setups(composite))


@pytest.mark.parametrize(
    "params",
    [
        {"min_width_atr": 5},
        {"min_width_atr": 5, "max_width_atr": 15},
        {"min_width_atr": 5, "max_width_atr": 5},
    ],
)
def test_valid_params_are_accepted(params: dict[str, Any]) -> None:
    check_ema_pullback_static_semantics(
        _spec_with_setups({"component_id": BAND, "instance_id": "b", "params": params})
    )


# -- semantics ------------------------------------------------------------------


def test_bounds_are_inclusive() -> None:
    width = (4.999, 5.0, 10.0, 15.0, 15.001)
    assert _mask(width, min_width_atr=5.0, max_width_atr=15.0) == (
        False,
        True,
        True,
        True,
        False,
    )


def test_no_upper_bound() -> None:
    width = (4.0, 5.0, 1000.0)
    assert _mask(width, min_width_atr=5.0) == (False, True, True)


def test_single_value_band() -> None:
    assert _mask((4.0, 5.0, 6.0), min_width_atr=5.0, max_width_atr=5.0) == (False, True, False)


def test_not_ready_bars_are_blocked_with_a_reason() -> None:
    mask, trace = _anchor_stack_width_band(
        _frame((6.0, None, 6.0)), COLUMNS, {"min_width_atr": 5.0}
    )
    assert mask == (True, False, True)
    assert trace["blocked_reason"] == ("", "indicator_not_ready", "")
    assert math.isnan(trace["width_atr"][1])


def test_blocked_reasons() -> None:
    _, trace = _anchor_stack_width_band(
        _frame((1.0, 6.0, 20.0)), COLUMNS, {"min_width_atr": 5.0, "max_width_atr": 15.0}
    )
    assert trace["blocked_reason"] == ("width_below_min", "", "width_above_max")
    assert trace["max_width_atr"] == (15.0, 15.0, 15.0)


def test_max_width_is_null_in_the_trace_when_absent() -> None:
    _, trace = _anchor_stack_width_band(_frame((6.0,)), COLUMNS, {"min_width_atr": 5.0})
    assert trace["max_width_atr"] == (None,)


# -- pipeline ---------------------------------------------------------------------


def _run(
    variants: list[dict[str, Any]], *, memo_enabled: bool = True
) -> tuple[list[Any], Any]:
    recorder = Recorder()
    with _capturing_contexts() as contexts, recording_services(
        recorder, memo_enabled=memo_enabled
    ) as services:
        ndjson = _drain_route(services, batch_payload(variants))
    assert ndjson["termination"]["kind"] == "complete", ndjson["termination"]
    for capture in recorder.captures:
        assert capture.exception is None, capture.exception
    return [capture.evaluation for capture in recorder.captures], contexts[0]


def _setup_masks(evaluation: Any, instance_id: str) -> dict[str, Any]:
    return {
        side.side: next(item for item in side.setups if item.instance_id == instance_id)
        for side in evaluation.setups
    }


def test_width_equals_the_existing_setup_width() -> None:
    old = _width("old", atr_period=48)
    new = _band("new", atr_period=48, min_width_atr=1.0)
    evaluations, _ = _run([_variant("both", _spec_with_setups(old, new))])
    old_trace = _setup_masks(evaluations[0], "old")["long"].trace["current_width_atr"]
    new_trace = _setup_masks(evaluations[0], "new")["long"].trace["width_atr"]
    assert len(old_trace) == len(new_trace)
    compared = 0
    for left, right in zip(old_trace, new_trace, strict=True):
        if math.isfinite(left) and math.isfinite(right):
            assert left == right
            compared += 1
        else:
            assert math.isnan(left) == math.isnan(right) or not math.isfinite(left)
    assert compared > 0


def test_band_mask_is_consistent_with_its_width_trace() -> None:
    item = _band("b", min_width_atr=3.0, max_width_atr=9.0)
    evaluations, _ = _run([_variant("one", _spec_with_setups(item))])
    masks = _setup_masks(evaluations[0], "b")
    for side, mask in masks.items():
        width = mask.trace["width_atr"]
        expected = tuple(math.isfinite(w) and 3.0 <= w <= 9.0 for w in width)
        assert mask.local_setup_allowed == expected, side
        assert any(expected)


def test_both_sides_get_the_same_mask() -> None:
    spec = _spec_with_setups(_band("b", min_width_atr=3.0))
    spec["trade_sides"] = {"enabled": ["long", "short"]}
    evaluations, _ = _run([_variant("both-sides", spec)])
    masks = _setup_masks(evaluations[0], "b")
    assert masks["long"].local_setup_allowed == masks["short"].local_setup_allowed


def test_composite_child_equals_the_plain_setup() -> None:
    plain = _band("plain", min_width_atr=3.0, max_width_atr=9.0)
    composite = {
        "component_id": "composite_setup",
        "instance_id": "combo",
        "params": {
            "children": [
                {
                    "child_id": "b",
                    "setup": {"component_id": BAND, "params": plain["params"]},
                }
            ],
            "paths": [{"path_id": "p", "require": ["b"]}],
        },
    }
    evaluations, _ = _run(
        [
            _variant("plain", _spec_with_setups(plain)),
            _variant("composite", _spec_with_setups(composite)),
        ]
    )
    left = _setup_masks(evaluations[0], "plain")
    right = _setup_masks(evaluations[1], "combo")
    for side in left:
        assert right[side].local_setup_allowed == left[side].local_setup_allowed
        assert any(left[side].local_setup_allowed)


def test_bounds_only_candidates_share_one_width_node() -> None:
    variants = [
        _variant(f"v{i}", _spec_with_setups(_band("b", min_width_atr=lo, max_width_atr=hi)))
        for i, (lo, hi) in enumerate([(5, 15), (6, 15), (5, 20), (5.0, 15.0)])
    ]
    on, context = _run(variants, memo_enabled=True)
    off, _ = _run(variants, memo_enabled=False)
    calls: Counter[str] = Counter()
    for identity, count in context.stats.compute_calls.items():
        calls[identity.kind] += count
    assert calls[NODE_WIDTH] == 1
    assert context.stats.unforeseen_consumptions == 0
    for left, right in zip(on, off, strict=True):
        for left_side, right_side in zip(left.setups, right.setups, strict=True):
            for left_mask, right_mask in zip(left_side.setups, right_side.setups, strict=True):
                assert left_mask.local_setup_allowed == right_mask.local_setup_allowed
                assert repr(left_mask.trace) == repr(right_mask.trace)  # NaN-safe
        assert left.entries == right.entries


def test_equivalent_bounds_share_the_local_node() -> None:
    variants = [
        _variant("a", _spec_with_setups(_band("b", min_width_atr=5))),
        _variant("b", _spec_with_setups(_band("b", min_width_atr=5.0))),
    ]
    _, context = _run(variants)
    calls: Counter[str] = Counter()
    for identity, count in context.stats.compute_calls.items():
        calls[identity.kind] += count
    assert calls[f"setup.{BAND}"] == 1


def test_absent_max_differs_from_any_present_max() -> None:
    variants = [
        _variant("a", _spec_with_setups(_band("b", min_width_atr=5))),
        _variant("b", _spec_with_setups(_band("b", min_width_atr=5, max_width_atr=1e9))),
    ]
    _, context = _run(variants)
    calls: Counter[str] = Counter()
    for identity, count in context.stats.compute_calls.items():
        calls[identity.kind] += count
    assert calls[f"setup.{BAND}"] == 2
    assert calls[NODE_WIDTH] == 1


# -- plan and history ---------------------------------------------------------------


def test_band_shares_the_atr_with_the_existing_width_setup() -> None:
    spec = _spec_with_setups(_width("old", atr_period=48), _band("new", atr_period=48))
    only_old = _spec_with_setups(_width("old", atr_period=48))
    with_both = build_feature_plan_from_canonical_spec(copy.deepcopy(spec))
    without = build_feature_plan_from_canonical_spec(copy.deepcopy(only_old))
    assert with_both.indicator_plan.plan_hash == without.indicator_plan.plan_hash


def test_plan_gains_exactly_one_atr_for_a_new_period() -> None:
    base = build_feature_plan_from_canonical_spec(
        _spec_with_setups(_untouched("u"))
    ).indicator_plan.features
    with_band = build_feature_plan_from_canonical_spec(
        _spec_with_setups(_untouched("u"), _band("b", atr_period=21))
    ).indicator_plan.features
    assert len(with_band) == len(base) + 1


def test_live_history_is_zero_additional() -> None:
    resolver = EmaPullbackLiveCalculationRequirements()
    reasons = [
        item
        for item in resolver.execute(_spec_with_setups(_band("b")))
        if "anchor_stack_width_band_setup" in item.reason
    ]
    assert len(reasons) == 1
    assert reasons[0].bars == 0
