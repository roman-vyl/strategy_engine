"""Tests for htf_regime_gate and shared context policy evaluation."""

from __future__ import annotations

import pytest

from research.strategies.ema_pullback.component_builders import (
    component_stack,
    context_consumption,
    direction_ema_anchor_stack,
    risk_no_filter,
    setup_untouched_anchor,
    trigger_reclaim_anchor,
)
from research.strategies.ema_pullback.context.consumption_validation import (
    validate_htf_regime_gate_params,
)
from research.strategies.ema_pullback.context.evaluation import (
    SideAwareEvaluationContext,
    evaluate_context_consumption,
)
from research.strategies.ema_pullback.context.policies import (
    EXIT_PROFILE_BY_HTF_STATE_POLICY,
    HTF_REGIME_GATE_POLICY,
    apply_exit_profile_by_htf_state,
    resolve_htf_regime,
)
from research.strategies.ema_pullback.features.calculations import add_feature_columns_from_plan
from research.strategies.ema_pullback.features.plan import build_feature_plan_from_strategy_spec
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec
from tests.ema_pullback_context_helpers import (
    blocker_htf_regime_gate,
    context_bundle_for_spec,
    htf_strategy_contexts,
)


@pytest.mark.parametrize(
    ("raw_state", "side", "expected"),
    [
        ("up", "long", "aligned"),
        ("down", "long", "countertrend"),
        ("neutral", "long", "neutral"),
        ("down", "short", "aligned"),
        ("up", "short", "countertrend"),
        ("neutral", "short", "neutral"),
    ],
)
def test_resolve_htf_regime_mapping_table(raw_state: str, side: str, expected: str) -> None:
    assert resolve_htf_regime(raw_state, side) == expected  # type: ignore[arg-type]


def test_htf_regime_gate_both_side_asymmetry_on_same_raw_bar() -> None:
    pytest.importorskip("pandas")
    import pandas as pd

    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(),
        components=component_stack(
            direction=direction_ema_anchor_stack(),
            blockers=(blocker_htf_regime_gate(allowed_regimes=("aligned",)),),
            trigger=trigger_reclaim_anchor(),
            risk=risk_no_filter(),
        ),
        enabled_sides=("long", "short"),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=1, freq="h", tz="UTC")
    close = pd.Series([100.0], index=idx)
    ohlcv = pd.DataFrame(
        {"close": close, "open": close, "high": close, "low": close, "volume": 1.0},
        index=idx,
    )
    df = add_feature_columns_from_plan(ohlcv, plan)
    cols = plan.htf_context_columns_for("htf")
    df[cols["fast"]] = [103.0]
    df[cols["anchor"]] = [102.0]
    df[cols["slow"]] = [101.0]
    bundle = context_bundle_for_spec(spec, df, plan)
    consumption = spec.components.blockers[0].context_consumption
    assert consumption is not None

    long_result = evaluate_context_consumption(
        consumption,
        SideAwareEvaluationContext(
            context_bundle=bundle,
            index=idx,
            evaluated_side="long",
        ),
    )
    short_result = evaluate_context_consumption(
        consumption,
        SideAwareEvaluationContext(
            context_bundle=bundle,
            index=idx,
            evaluated_side="short",
        ),
    )
    assert bool(long_result.allowed_mask.iloc[0]) is True
    assert bool(short_result.allowed_mask.iloc[0]) is False


def test_regime_cache_reused_for_same_context_ref_and_side() -> None:
    pytest.importorskip("pandas")
    import pandas as pd

    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(),
        components=component_stack(
            direction=direction_ema_anchor_stack(),
            blockers=(blocker_htf_regime_gate(allowed_regimes=("aligned", "neutral")),),
            trigger=trigger_reclaim_anchor(),
            risk=risk_no_filter(),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=2, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0], index=idx)
    ohlcv = pd.DataFrame(
        {"close": close, "open": close, "high": close, "low": close, "volume": 1.0},
        index=idx,
    )
    df = add_feature_columns_from_plan(ohlcv, plan)
    cols = plan.htf_context_columns_for("htf")
    df[cols["fast"]] = [103.0, 101.0]
    df[cols["anchor"]] = [102.0, 102.0]
    df[cols["slow"]] = [101.0, 103.0]
    bundle = context_bundle_for_spec(spec, df, plan)
    consumption = spec.components.blockers[0].context_consumption
    assert consumption is not None
    cache: dict = {}
    eval_ctx = SideAwareEvaluationContext(
        context_bundle=bundle,
        index=idx,
        evaluated_side="long",
        regime_cache=cache,
    )
    first = evaluate_context_consumption(
        context_consumption(
            context_ref=consumption.context_ref,
            policy_id=HTF_REGIME_GATE_POLICY,
            params=(("allowed_regimes", ["aligned"]),),
        ),
        eval_ctx,
    )
    assert ("htf", "long") in cache
    second = evaluate_context_consumption(consumption, eval_ctx)
    assert first.resolved_regime_series is not None
    assert second.resolved_regime_series is not None
    assert first.resolved_regime_series.tolist() == second.resolved_regime_series.tolist()


def test_validate_htf_regime_gate_params() -> None:
    validate_htf_regime_gate_params({"allowed_regimes": ["aligned"]}, path="policy")
    with pytest.raises(ValueError, match="required"):
        validate_htf_regime_gate_params({}, path="policy")
    with pytest.raises(ValueError, match="non-empty"):
        validate_htf_regime_gate_params({"allowed_regimes": []}, path="policy")
    with pytest.raises(ValueError, match="invalid values"):
        validate_htf_regime_gate_params({"allowed_regimes": ["bullish"]}, path="policy")


def test_exit_profile_requires_enabled_sides() -> None:
    pytest.importorskip("pandas")
    import pandas as pd

    from research.strategies.ema_pullback.component_builders import exit_rsi, trade_management
    from tests.ema_pullback_context_helpers import exit_policy_htf_consumption

    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(),
        components=component_stack(
            direction=direction_ema_anchor_stack(),
            blockers=(blocker_htf_regime_gate(),),
            trigger=trigger_reclaim_anchor(),
            risk=risk_no_filter(),
        ),
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(
                always_on=make_ema_pullback_strategy_spec().trade_management.exit_policy.always_on.exits,
                aligned=(exit_rsi(instance_id="profile_exit"),),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=1, freq="h", tz="UTC")
    close = pd.Series([100.0], index=idx)
    ohlcv = pd.DataFrame(
        {"close": close, "open": close, "high": close, "low": close, "volume": 1.0},
        index=idx,
    )
    df = add_feature_columns_from_plan(ohlcv, plan)
    cols = plan.htf_context_columns_for("htf")
    df[cols["fast"]] = [103.0]
    df[cols["anchor"]] = [102.0]
    df[cols["slow"]] = [101.0]
    bundle = context_bundle_for_spec(spec, df, plan)
    consumption = spec.trade_management.exit_policy.context_consumption
    assert consumption is not None

    with pytest.raises(ValueError, match="enabled_sides"):
        evaluate_context_consumption(
            consumption,
            SideAwareEvaluationContext(context_bundle=bundle, index=idx),
        )


def test_exit_profile_profiles_use_reindexed_raw_state() -> None:
    pytest.importorskip("pandas")
    import pandas as pd

    full_idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    subset_idx = full_idx[:2]
    raw_state = pd.Series(["up", "down"], index=subset_idx)
    policy = context_consumption(
        context_ref="htf",
        policy_id=EXIT_PROFILE_BY_HTF_STATE_POLICY,
    ).policy

    profile_long, profile_short = apply_exit_profile_by_htf_state(
        raw_state,
        policy=policy,
        index=full_idx,
        sides=("long", "short"),
    )

    assert profile_long.index.equals(full_idx)
    assert profile_long.tolist() == ["aligned", "countertrend", "neutral"]
    assert profile_short.tolist() == ["countertrend", "aligned", "neutral"]
