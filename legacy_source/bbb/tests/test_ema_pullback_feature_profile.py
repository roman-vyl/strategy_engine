from __future__ import annotations

from dataclasses import replace

import pytest

from research.strategies.ema_pullback.spec import (
    AnchorStackSpec,
    AtrDistanceSpec,
    EmaSpec,
    ExitRuleSpec,
    strategy_spec_config_id,
)
from research.strategies.ema_pullback.features.plan import build_feature_plan_from_strategy_spec
from research.strategies.ema_pullback.spec_instances import (
    make_ema_pullback_strategy_spec,
    variant_from_spec,
)


def test_default_spec_factory_is_valid_strategy_spec() -> None:
    spec = make_ema_pullback_strategy_spec()
    assert spec.variant.strip()
    assert spec.variant == variant_from_spec(spec)
    assert spec.symbol.strip()
    assert spec.base_timeframe.strip()
    stack = spec.anchor_stack
    assert stack.fast.period < stack.anchor.period < stack.slow.period
    assert spec.components.direction == "ema_anchor_stack_trend"
    assert spec.setups[0].component_id == "untouched_anchor_setup"
    assert spec.components.trigger.component_id == "reclaim_anchor"
    assert [b.component_id for b in spec.components.blockers] == ["no_blockers"]
    always_on = spec.trade_management.exit_policy.always_on.exits
    assert [e.component_id for e in always_on] == ["atr_stop_loss", "atr_take_profit"]
    stop = [r for r in always_on if r.exit_kind == "stop_loss"]
    take = [r for r in always_on if r.exit_kind == "take_profit"]
    assert len(stop) == 1 and len(take) == 1


def test_strategy_spec_config_id_is_deterministic() -> None:
    a = make_ema_pullback_strategy_spec()
    b = make_ema_pullback_strategy_spec()
    assert strategy_spec_config_id(a) == strategy_spec_config_id(b)


def test_invalid_anchor_stack_order_rejected() -> None:
    with pytest.raises(ValueError, match="fast < anchor < slow"):
        AnchorStackSpec(
            fast=EmaSpec(source="close", timeframe="base", period=20),
            anchor=EmaSpec(source="close", timeframe="base", period=10),
            slow=EmaSpec(source="close", timeframe="base", period=1000),
        )


def test_exit_distance_rules_require_distance() -> None:
    with pytest.raises(ValueError, match="atr_stop_loss exit requires distance"):
        ExitRuleSpec(instance_id="atr_stop_loss", component_id="atr_stop_loss", exit_kind="stop_loss")


def test_exit_rule_rejects_component_kind_mismatch() -> None:
    distance = AtrDistanceSpec(timeframe="base", period=14, multiplier=1.5)
    with pytest.raises(ValueError, match="rsi_signal_exit.*exit_kind 'signal'"):
        ExitRuleSpec(
            instance_id="rsi_exit",
            component_id="rsi_signal_exit",
            exit_kind="stop_loss",
            distance=distance,
        )


def test_signal_exit_rules_reject_distance_payload() -> None:
    distance = AtrDistanceSpec(timeframe="base", period=14, multiplier=1.5)
    with pytest.raises(ValueError, match="signal exit must not define distance"):
        ExitRuleSpec(
            instance_id="rsi_exit",
            component_id="rsi_signal_exit",
            exit_kind="signal",
            distance=distance,
        )


def test_distance_exit_rules_reject_signal_thresholds() -> None:
    distance = AtrDistanceSpec(timeframe="base", period=14, multiplier=1.5)
    with pytest.raises(ValueError, match="stop_loss exit must not define signal thresholds"):
        ExitRuleSpec(
            instance_id="atr_stop_loss",
            component_id="atr_stop_loss",
            exit_kind="stop_loss",
            distance=distance,
            long_exit_above=70.0,
        )


def test_constant_usd_stop_requires_positive_usd_distance() -> None:
    with pytest.raises(ValueError, match="constant_usd_stop_loss exit requires positive usd_distance"):
        ExitRuleSpec(
            instance_id="sl",
            component_id="constant_usd_stop_loss",
            exit_kind="stop_loss",
        )


def test_atr_stop_rejects_usd_distance() -> None:
    distance = AtrDistanceSpec(timeframe="base", period=14, multiplier=1.5)
    with pytest.raises(ValueError, match="atr_stop_loss exit must not define usd_distance"):
        ExitRuleSpec(
            instance_id="sl",
            component_id="atr_stop_loss",
            exit_kind="stop_loss",
            distance=distance,
            usd_distance=100.0,
        )


def test_default_always_on_spec_has_no_strategy_contexts() -> None:
    spec = make_ema_pullback_strategy_spec()
    assert spec.contexts == ()
    assert spec.trade_management.exit_policy.context_consumption is None
    plan = build_feature_plan_from_strategy_spec(spec)
    assert plan.htf_context_columns_by_ref == {}
    assert not any("4h" in feature.feature_id for feature in plan.features)


def test_spec_with_exit_context_consumption_has_htf_provider() -> None:
    from research.strategies.ema_pullback.component_builders import exit_rsi, trade_management
    from tests.ema_pullback_context_helpers import exit_policy_htf_consumption, htf_strategy_contexts

    base = make_ema_pullback_strategy_spec()
    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(),
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(
                always_on=base.trade_management.exit_policy.always_on.exits,
                aligned=(exit_rsi(instance_id="rsi_profile"),),
            ),
        ),
    )
    assert spec.trade_management.exit_policy.context_consumption is not None
    assert spec.contexts_by_ref()["htf"].component_id == "htf_context"
    plan = build_feature_plan_from_strategy_spec(spec)
    assert "htf" in plan.htf_context_columns_by_ref


def test_factory_adds_htf_provider_when_consumption_without_explicit_contexts() -> None:
    from research.strategies.ema_pullback.component_builders import exit_rsi, trade_management
    from tests.ema_pullback_context_helpers import exit_policy_htf_consumption

    spec = make_ema_pullback_strategy_spec(
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(
                always_on=make_ema_pullback_strategy_spec().trade_management.exit_policy.always_on.exits,
                aligned=(exit_rsi(instance_id="rsi_profile"),),
            ),
        ),
    )
    assert spec.contexts_by_ref()["htf"].component_id == "htf_context"


def test_component_stack_uses_typed_rule_specs() -> None:
    spec = make_ema_pullback_strategy_spec()
    assert spec.components.trigger.component_id == "reclaim_anchor"
    assert isinstance(spec.components.blockers, tuple)
    assert spec.components.blockers[0].component_id == "no_blockers"
    assert isinstance(spec.trade_management.exit_policy.always_on.exits, tuple)
    assert spec.trade_management.exit_policy.always_on.exits[0].component_id == "atr_stop_loss"


def test_strategy_spec_requires_non_empty_identity_fields() -> None:
    with pytest.raises(ValueError, match="variant must be non-empty"):
        replace(make_ema_pullback_strategy_spec(), variant="")
