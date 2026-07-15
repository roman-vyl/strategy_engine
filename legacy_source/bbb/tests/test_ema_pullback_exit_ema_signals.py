from __future__ import annotations

import pytest

pytest.importorskip("pandas")

import pandas as pd

from research.strategies.ema_pullback import component_builders as builders
from research.strategies.ema_pullback.component_builders import (
    ema,
    exit_ema_close_loss,
    exit_ema_cross_loss,
    trade_management,
)
from tests.ema_pullback_context_helpers import (
    build_exit_outputs_with_context_bundle,
    exit_policy_htf_consumption,
    htf_strategy_contexts,
)
from research.strategies.ema_pullback.components.exits import ema_close_loss_exit, ema_cross_loss_exit
from research.strategies.ema_pullback.features.plan import build_feature_plan_from_strategy_spec
from research.strategies.ema_pullback.instance_loader import (
    EmaPullbackInstanceValidationError,
    _parse_exit,
)
from research.strategies.ema_pullback.spec import ExitRuleSpec, RsiFeatureSpec
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec


def test_ema_close_loss_requires_ema_forbids_cross_fields() -> None:
    with pytest.raises(ValueError, match="ema_close_loss_exit requires ema"):
        ExitRuleSpec(instance_id="x", component_id="ema_close_loss_exit", exit_kind="signal")
    with pytest.raises(ValueError, match="must not define fast_ema"):
        ExitRuleSpec(
            instance_id="x",
            component_id="ema_close_loss_exit",
            exit_kind="signal",
            ema=ema(200),
            fast_ema=ema(100),
        )


def test_ema_cross_loss_requires_same_timeframe() -> None:
    with pytest.raises(ValueError, match="same timeframe"):
        ExitRuleSpec(
            instance_id="x",
            component_id="ema_cross_loss_exit",
            exit_kind="signal",
            fast_ema=ema(100, timeframe="5m"),
            slow_ema=ema(200, timeframe="1h"),
        )


def test_ema_cross_loss_forbids_ema_field() -> None:
    with pytest.raises(ValueError, match="must not define ema"):
        ExitRuleSpec(
            instance_id="x",
            component_id="ema_cross_loss_exit",
            exit_kind="signal",
            ema=ema(200),
            fast_ema=ema(100),
            slow_ema=ema(200),
        )


def test_confirm_bars_defaults_to_one() -> None:
    rule = exit_ema_close_loss(instance_id="c", ema=ema(200))
    assert rule.confirm_bars == 1


def test_ema_close_loss_confirm_bars_on_base_index() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="5min", tz="UTC")
    close = pd.Series([100.0, 99.0, 98.0, 97.0, 96.0], index=idx)
    ema_vals = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    df = pd.DataFrame({"close": close, "ema_1h_200": ema_vals}, index=idx)
    rule = exit_ema_close_loss(instance_id="c", ema=ema(200, timeframe="1h"), confirm_bars=3)

    out = ema_close_loss_exit(df, side="long", rule=rule, ema_col="ema_1h_200")
    assert out.tolist() == [False, False, False, True, True]


def test_ema_cross_loss_cross_event_confirm_one() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    fast = pd.Series([102.0, 101.0, 99.0, 98.0], index=idx)
    slow = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    df = pd.DataFrame({"ema_fast": fast, "ema_slow": slow}, index=idx)
    rule = exit_ema_cross_loss(
        instance_id="x",
        fast_ema=ema(100),
        slow_ema=ema(200),
        confirm_bars=1,
    )

    out = ema_cross_loss_exit(df, side="long", rule=rule, fast_col="ema_fast", slow_col="ema_slow")
    assert out.tolist() == [False, False, True, False]


def test_ema_cross_loss_confirm_three_requires_cross_in_window() -> None:
    idx = pd.date_range("2024-01-01", periods=6, freq="h", tz="UTC")
    fast = pd.Series([102.0, 101.0, 99.0, 98.0, 97.0, 96.0], index=idx)
    slow = pd.Series([100.0] * 6, index=idx)
    df = pd.DataFrame({"ema_fast": fast, "ema_slow": slow}, index=idx)
    rule = exit_ema_cross_loss(
        instance_id="x",
        fast_ema=ema(100),
        slow_ema=ema(200),
        confirm_bars=3,
    )

    out = ema_cross_loss_exit(df, side="long", rule=rule, fast_col="ema_fast", slow_col="ema_slow")
    assert out.tolist() == [False, False, False, False, True, False]


def test_ema_cross_loss_confirm_three_no_exit_without_cross() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    fast = pd.Series([98.0, 97.0, 96.0, 95.0, 94.0], index=idx)
    slow = pd.Series([100.0] * 5, index=idx)
    df = pd.DataFrame({"ema_fast": fast, "ema_slow": slow}, index=idx)
    rule = exit_ema_cross_loss(
        instance_id="x",
        fast_ema=ema(100),
        slow_ema=ema(200),
        confirm_bars=3,
    )

    out = ema_cross_loss_exit(df, side="long", rule=rule, fast_col="ema_fast", slow_col="ema_slow")
    assert not bool(out.any())


def test_feature_plan_includes_exit_ema_outside_stack() -> None:
    base = make_ema_pullback_strategy_spec()
    spec = make_ema_pullback_strategy_spec(
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(
                always_on=base.trade_management.exit_policy.always_on.exits,
                aligned=(exit_ema_cross_loss(instance_id="cross", fast_ema=ema(100), slow_ema=ema(200)),),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    assert plan.ema_column(ema(100)) == "ema_close_base_100"


def test_profile_only_aligned_exit_not_in_countertrend_series() -> None:
    base = make_ema_pullback_strategy_spec()
    close_rule = exit_ema_close_loss(instance_id="ema_close", ema=ema(200), confirm_bars=1)
    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(),
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(
                always_on=(),
                aligned=(close_rule,),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=6, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "close": [100.0, 99.0, 98.0, 97.0, 96.0, 95.0],
            plan.ema_column(ema(200)): [100.0] * 6,
            plan.htf_context_columns["fast"]: [110.0] * 6,
            plan.htf_context_columns["anchor"]: [105.0] * 6,
            plan.htf_context_columns["slow"]: [90.0] * 6,
        },
        index=idx,
    )

    out = build_exit_outputs_with_context_bundle(df, spec, plan)
    assert bool(out.long_exits_by_profile["aligned"].any())
    assert not bool(out.long_exits_by_profile["countertrend"].any())


def test_parse_exit_nested_ema_block() -> None:
    rule = _parse_exit(
        0,
        {
            "instance_id": "c1",
            "component_id": "ema_close_loss_exit",
            "ema": {"timeframe": "1h", "source": "close", "period": 200},
            "confirm_bars": 3,
        },
    )
    assert rule.ema is not None
    assert rule.ema.timeframe == "1h"
    assert rule.confirm_bars == 3


def test_parse_exit_rejects_flat_ema_without_nested_block() -> None:
    with pytest.raises(EmaPullbackInstanceValidationError, match="unknown field"):
        _parse_exit(
            0,
            {
                "instance_id": "c1",
                "component_id": "ema_close_loss_exit",
                "timeframe": "1h",
                "period": 200,
            },
        )


def test_parse_cross_exit_rejects_mismatched_timeframes() -> None:
    with pytest.raises(ValueError, match="same timeframe"):
        _parse_exit(
            0,
            {
                "instance_id": "x",
                "component_id": "ema_cross_loss_exit",
                "fast_ema": {"timeframe": "5m", "source": "close", "period": 100},
                "slow_ema": {"timeframe": "1h", "source": "close", "period": 200},
            },
        )


def test_close_loss_forbids_rsi_payload() -> None:
    with pytest.raises(ValueError, match="must not define rsi"):
        ExitRuleSpec(
            instance_id="x",
            component_id="ema_close_loss_exit",
            exit_kind="signal",
            ema=ema(200),
            rsi=RsiFeatureSpec(),
        )
