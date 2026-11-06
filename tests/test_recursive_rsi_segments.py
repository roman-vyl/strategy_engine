from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from test_rsi_indicator import market_frame

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import IndicatorPlan, PlannedFeature
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator
from strategy_engine.indicators.implementations.rsi import rsi_recursive
from strategy_engine.service.registries import IndicatorRegistry
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate, segment_values
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode
from strategy_engine.strategies.live_calculation.indicator_requirements import (
    ResolveIndicatorHistoryRequirements,
)


def segment(**kw):
    payload = dict(
        episode="trend",
        of={"kind": "rsi_ewm", "params": {"period": 168}},
        aggregate="min",
        value="level",
        **{"from": "peak", "to": "current"},
    )
    payload.update(kw)
    return parse_predicate(
        {"kind": "range", "operand": {"segment": payload}, "min": None, "max": None},
        "p",
        episode_refs=["trend"],
    ).long.operand.segment


def episode():
    return SideEpisode(
        "long",
        {"touch_number": np.array([1.0, 1.0, 1.0, 2.0, 2.0, 2.0]), "episode_id": np.zeros(6)},
        {},
        {},
        {},
        {
            "origin_bar": np.array([0.0, 2.0]),
            "peak_bar": np.array([0.0, 3.0]),
            "touch_bar": np.array([1.0, 3.0]),
        },
        np.array([0]),
    )


@pytest.mark.parametrize("period", [1, 3, 168])
def test_recursive_reference_and_causality(period):
    x = pd.Series(100 + np.random.default_rng(4).normal(size=1000).cumsum())
    delta = x.diff().fillna(0)
    u = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    d = (-delta).clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    expected = 100 * u / (u + d)
    np.testing.assert_allclose(rsi_recursive(x, period=period), expected, atol=1e-9)
    np.testing.assert_allclose(rsi_recursive(x[:500], period=period), expected[:500])
    assert rsi_recursive(pd.Series([1.0, 1.0, 1.0]), period=period).isna().all()
    assert rsi_recursive(pd.Series([1.0, 2.0, 3.0]), period=period).iloc[-1] == 100
    assert rsi_recursive(pd.Series([3.0, 2.0, 1.0]), period=period).iloc[-1] == 0
    assert (
        rsi_recursive(pd.Series([1.0, 2.0, np.nan, 3.0, 4.0]), period=period).iloc[2:].isna().all()
    )


def test_indicator_pipeline_and_history():
    f = PlannedFeature("r", "rsi_ewm", "base", "close", {"period": 3})
    registry = IndicatorRegistry()
    registry.validate_feature(f)
    assert registry.get_schema("rsi_ewm")["compatibility_profile"] == "recursive_zero_seed_v1"
    values = (
        RangeIndicatorEvaluator()
        .evaluate(market_frame(["1", "2", "3", "2", "4"]), IndicatorPlan("1", (f,)))
        .series["r"]
    )
    expected = rsi_recursive(pd.Series([1.0, 2.0, 3.0, 2.0, 4.0]), period=3)
    np.testing.assert_allclose([np.nan if v is None else float(v) for v in values], expected)
    assert ResolveIndicatorHistoryRequirements().execute(IndicatorPlan("1", (f,)))[0].bars > 3
    for n in [True, 0, -1, "3", 1.2]:
        with pytest.raises(InvalidRequestError):
            registry.validate_feature(replace(f, parameters={"period": n}))


def test_interval_boundaries_and_previous():
    ep = episode()
    x = np.array([99.0, 10.0, 20.0, 90.0, 40.0, 5.0])
    cur = segment(include_start=False, empty_policy="end")
    np.testing.assert_allclose(segment_values(ep, x, cur), [99, 10, 10, 90, 40, 5])
    prev = segment(touch="previous", to="next_origin", include_start=False)
    np.testing.assert_allclose(segment_values(ep, x, prev), [np.nan] * 3 + [10] * 3)
    assert np.isnan(segment_values(ep, x, replace(cur, empty_policy="missing"))[3])
    assert segment_values(ep, x, replace(cur, last_n=1))[5] == 5
    assert segment_values(ep, x, replace(cur, aggregate="max"))[5] == 40
    x[4] = np.nan
    assert np.isnan(segment_values(ep, x, cur)[5])
    assert segment_values(ep, x, replace(cur, last_n=1))[5] == 5
    invalid = replace(ep, touches={**ep.touches, "peak_bar": np.array([0.0, 8.0])})
    assert np.isnan(segment_values(invalid, x, cur)[3:]).all()
    for kwargs in [
        dict(include_start=1),
        dict(empty_policy="oops"),
        dict(aggregate="sum", include_start=False),
    ]:
        with pytest.raises(InvalidRequestError):
            segment(**kwargs)


def test_manifest_pipeline_and_identity():
    import json
    from pathlib import Path

    from parity.corpus import _variant
    from test_ema_pullback_predicates_a2 import _segment_identity
    from test_ema_pullback_stack_episode_e2e import _run

    from strategy_engine.domain.node_identity import node_spec
    from strategy_engine.strategies.ema_pullback.stack_episode import episode_identity_key

    spec = json.loads((Path(__file__).parents[1] / "examples/c6-original.json").read_text())
    recorder, context = _run([_variant("c6", spec)])
    assert len(recorder.captures) == 1
    assert context.stats.unforeseen_consumptions == 0

    def identity(**fields):
        pred, ids, resolve = _segment_identity(**fields)
        ep = node_spec("episode.ema_stack", version=1, params={"ref": "trend"}, side="long")
        return resolve(pred, ids, "long", contexts={episode_identity_key("trend", "long"): ep})

    default = identity(value="level", aggregate="min")
    assert default == identity(
        value="level", aggregate="min", include_start=True, empty_policy="missing"
    )
    assert default != identity(value="level", aggregate="min", include_start=False)


def test_recursive_htf_completion_and_empty_input():
    f = PlannedFeature("r", "rsi_ewm", "1h", "close", {"period": 3})
    result = RangeIndicatorEvaluator().evaluate(
        market_frame([str(100 + i) for i in range(48)]), IndicatorPlan("1", (f,))
    )
    # The second hourly close is the first nonflat recursion, visible at 02:00.
    assert all(v is None for v in result.series["r"][:24])
    assert float(result.series["r"][24]) == 100
    assert len(rsi_recursive(pd.Series([], dtype=float), period=168)) == 0
