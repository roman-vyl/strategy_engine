"""Completed HTF reads at the close of the selected base candle."""

from dataclasses import replace
from decimal import Decimal

import pytest
from test_atr_indicator import market_frame

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import IndicatorPlan
from strategy_engine.indicators.feature_kinds import plan_feature_request
from strategy_engine.indicators.implementations.range_evaluator import (
    RangeIndicatorEvaluator,
    resolve_feature,
)
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate


def test_close_boundary_is_available_on_closed_prefix_without_future_row() -> None:
    f = market_frame(721)
    bars = list(f.bars)
    bars[719] = replace(bars[719], high=Decimal("5000"))
    f = replace(f, bars=tuple(bars))
    legacy = plan_feature_request("atr_wilder", "4h", None, {"period": 14})
    close = plan_feature_request("atr_wilder", "4h", None, {"period": 14}, availability="bar_close")
    plan = IndicatorPlan("availability", (legacy, close))
    ev = RangeIndicatorEvaluator()
    full = ev.evaluate_native(f, plan)
    old, new = full.series[legacy.output_id], full.series[close.output_id]
    # Index 719 closes 4h bucket 14; the prefix contains no index 720.
    for n in (718, 719, 720):
        prefix = replace(
            f,
            bars=f.bars[: n + 1],
            requested_range=replace(f.requested_range, to_ms=(n + 1) * 300000),
        )
        result = ev.evaluate_native(prefix, plan)
        assert result.series[close.output_id][-1] == new[n]
        assert result.series[legacy.output_id][-1] == old[n]
    assert new[719] == old[720]
    assert new[719] != old[719]
    assert new[718] == old[718]
    assert new[719] is not None
    assert old[670] is None and new[670] is None
    assert new[671] is not None and old[671] is None


def test_availability_separates_identity_and_column_without_changing_default() -> None:
    a = plan_feature_request("atr_wilder", "4h", None, {"period": 14})
    b = plan_feature_request("atr_wilder", "4h", None, {"period": 14}, availability="bar_close")
    assert a.output_id == "atr_wilder_close_4h_14"
    assert "availability" not in a.canonical_payload()
    assert b.output_id != a.output_id
    assert resolve_feature(a, base_timeframe="5m", upstream={}) != resolve_feature(
        b, base_timeframe="5m", upstream={}
    )
    pred = parse_predicate(
        {
            "kind": "range",
            "operand": {
                "at_point": {
                    "episode": "trend",
                    "point": "peak",
                    "operand": {
                        "feature": {
                            "kind": "atr_wilder",
                            "timeframe": "4h",
                            "availability": "bar_close",
                            "params": {"period": 14},
                        }
                    },
                }
            },
            "min": 0,
            "max": None,
        },
        "test",
        episode_refs=["trend"],
    )
    assert pred.features()[0].availability == "bar_close"


@pytest.mark.parametrize("invalid", ["next_bar", "", None, True])
def test_invalid_availability_fails_closed(invalid: object) -> None:
    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {
                "kind": "range",
                "operand": {
                    "feature": {
                        "kind": "atr_wilder",
                        "timeframe": "4h",
                        "availability": invalid,
                        "params": {"period": 14},
                    }
                },
                "min": 0,
                "max": None,
            },
            "test",
        )
