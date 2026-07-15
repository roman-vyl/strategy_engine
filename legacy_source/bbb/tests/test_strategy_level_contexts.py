"""Strategy-level contexts and exit policy consumption."""

from __future__ import annotations

import pytest

from research.strategies.ema_pullback.component_builders import (
    blocker_counter_candle,
    blocker_rule,
    component_stack,
    context_consumption,
    context_provider,
    direction_ema_anchor_stack,
    exit_policy,
    risk_no_filter,
    setup_untouched_anchor,
    strategy_contexts,
    trigger_reclaim_anchor,
)
from research.strategies.ema_pullback.components.registry import NO_BLOCKERS_COMPONENT, resolve_component
from research.strategies.ema_pullback.context.bundle import ContextBundle
from research.strategies.ema_pullback.context.pipeline import build_context_bundle_for_spec
from research.strategies.ema_pullback.context.policies import HTF_REGIME_GATE_POLICY
from research.strategies.ema_pullback.execution.exits import build_exit_outputs_from_spec
from research.strategies.ema_pullback.execution.signals import (
    _apply_blocker_context_gate,
    build_signals_from_spec,
)
from research.strategies.ema_pullback.context.policies import EXIT_PROFILE_BY_HTF_STATE_POLICY
from research.strategies.ema_pullback.features.calculations import add_feature_columns_from_plan
from research.strategies.ema_pullback.features.plan import build_feature_plan_from_strategy_spec
from research.strategies.ema_pullback.instance_loader import (
    EmaPullbackInstanceValidationError,
    load_ema_pullback_instance,
)
from research.strategies.ema_pullback.spec import ContextConsumptionSpec, ExitPolicySpec
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec
from tests.ema_pullback_context_helpers import (
    blocker_htf_regime_gate,
    exit_policy_htf_consumption,
    htf_strategy_contexts,
)


def test_exit_policy_rejects_profile_exits_without_consumption() -> None:
    from research.strategies.ema_pullback.component_builders import exit_rsi

    base = make_ema_pullback_strategy_spec()
    with pytest.raises(ValueError, match="context_consumption is required"):
        ExitPolicySpec(
            always_on=base.trade_management.exit_policy.always_on,
            profiles=exit_policy_htf_consumption(
                aligned=(exit_rsi(instance_id="profile_exit"),),
            ).profiles,
            context_consumption=None,
        )


def test_always_on_only_exit_policy_without_consumption_is_valid() -> None:
    spec = make_ema_pullback_strategy_spec()
    assert spec.trade_management.exit_policy.context_consumption is None
    assert spec.contexts == ()


def test_factory_adds_default_htf_when_exit_consumption_without_contexts() -> None:
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
    assert "htf" in spec.contexts_by_ref()


def test_context_ref_keys_are_case_sensitive() -> None:
    spec = make_ema_pullback_strategy_spec(
        contexts=strategy_contexts(
            (
                ("htf", context_provider(timeframe="4h", fast_period=10, anchor_period=20, slow_period=30)),
                ("HTF", context_provider(timeframe="1d", fast_period=11, anchor_period=21, slow_period=31)),
            )
        ),
    )
    assert set(spec.contexts_by_ref()) == {"htf", "HTF"}


def test_loader_rejects_exit_policy_context() -> None:
    instance = {
        "instance_id": "legacy",
        "variant": "v",
        "market": {"symbol": "BTCUSDT", "base_timeframe": "1h"},
        "strategy": {
            "trade_sides": ["long"],
            "anchor_stack": {"source": "close", "timeframe": "base", "fast": 100, "anchor": 200, "slow": 1000},
            "direction": {"component_id": "ema_anchor_stack_trend"},
            "setup": {"component_id": "untouched_anchor_setup", "lookback": 50, "active_bars": 3},
            "trigger": {"component_id": "reclaim_anchor"},
            "blockers": [{"instance_id": "no_blockers", "component_id": "no_blockers"}],
            "risk": {"component_id": "no_risk_filter"},
            "contexts": {},
            "trade_management": {
                "exit_policy": {
                    "context": {
                        "component_id": "htf_context",
                        "timeframe": "4h",
                        "source": "close",
                        "fast_period": 100,
                        "anchor_period": 200,
                        "slow_period": 1000,
                    },
                    "always_on": {"exits": []},
                    "profiles": {
                        "aligned": {"exits": []},
                        "countertrend": {"exits": []},
                        "neutral": {"exits": []},
                    },
                }
            },
        },
    }
    with pytest.raises(EmaPullbackInstanceValidationError, match="exit_policy.context is no longer supported"):
        load_ema_pullback_instance(instance)


def test_context_bundle_builds_per_ref() -> None:
    pytest.importorskip("pandas")
    import pandas as pd

    from research.strategies.ema_pullback.component_builders import trade_management
    from tests.ema_pullback_context_helpers import exit_policy_htf_consumption, htf_strategy_contexts

    from research.strategies.ema_pullback.component_builders import exit_rsi

    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(),
        trade_management_spec=trade_management(
            exit_policy_spec=exit_policy_htf_consumption(
                always_on=make_ema_pullback_strategy_spec().trade_management.exit_policy.always_on.exits,
                aligned=(exit_rsi(instance_id="rsi_profile"),),
            ),
        ),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0], index=idx)
    df = pd.DataFrame({"close": close, "open": close, "high": close, "low": close, "volume": 1.0}, index=idx)
    for col in plan.htf_context_columns_for("htf").values():
        df[col] = close
    bundle = ContextBundle.build(spec, df, plan)
    assert bundle.has("htf")
    assert bundle.get("htf").state_series().tolist() == ["neutral", "neutral", "neutral"]


def test_loader_rejects_blocker_unknown_context_ref() -> None:
    instance = {
        "instance_id": "gate",
        "variant": "v",
        "market": {"symbol": "BTCUSDT", "base_timeframe": "1h"},
        "strategy": {
            "trade_sides": ["long"],
            "anchor_stack": {"source": "close", "timeframe": "base", "fast": 100, "anchor": 200, "slow": 1000},
            "direction": {"component_id": "ema_anchor_stack_trend"},
            "setup": {"component_id": "untouched_anchor_setup", "lookback": 50, "active_bars": 3},
            "trigger": {"component_id": "reclaim_anchor"},
            "blockers": [
                {
                    "instance_id": "ccb",
                    "component_id": "counter_candle_blocker",
                    "context_consumption": {
                        "context_ref": "missing",
                        "policy": {
                            "policy_id": HTF_REGIME_GATE_POLICY,
                            "params": {"allowed_regimes": ["aligned"]},
                        },
                    },
                }
            ],
            "risk": {"component_id": "no_risk_filter"},
            "contexts": {
                "htf": {
                    "component_id": "htf_context",
                    "timeframe": "4h",
                    "source": "close",
                    "fast_period": 100,
                    "anchor_period": 200,
                    "slow_period": 1000,
                }
            },
            "trade_management": {
                "exit_policy": {
                    "always_on": {
                        "exits": [
                            {
                                "instance_id": "atr_sl",
                                "component_id": "atr_stop_loss",
                                "distance": {"timeframe": "base", "period": 14, "multiplier": 1.5},
                            }
                        ]
                    },
                    "profiles": {
                        "aligned": {"exits": []},
                        "countertrend": {"exits": []},
                        "neutral": {"exits": []},
                    },
                }
            },
        },
    }
    with pytest.raises(ValueError, match="missing"):
        load_ema_pullback_instance(instance)


def test_htf_regime_gate_changes_blocker_mask_and_omitting_consumption_restores_baseline() -> None:
    pytest.importorskip("pandas")
    import pandas as pd

    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [10.0, 10.0, 10.0],
            "close": [11.0, 11.0, 11.0],
            "high": [11.0, 11.0, 11.0],
            "low": [10.0, 10.0, 10.0],
            "volume": [1.0, 1.0, 1.0],
        },
        index=idx,
    )

    rule_baseline = blocker_counter_candle()
    rule_gate_aligned = blocker_htf_regime_gate(allowed_regimes=("aligned",))
    rule_gate_aligned_counter = blocker_htf_regime_gate(
        allowed_regimes=("aligned", "countertrend"),
    )

    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(),
        components=component_stack(
            direction=direction_ema_anchor_stack(),
            blockers=(rule_gate_aligned,),
            trigger=trigger_reclaim_anchor(),
            risk=risk_no_filter(),
        ),
        enabled_sides=("long",),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    cols = plan.htf_context_columns_for("htf")
    df[cols["fast"]] = [103.0, 101.0, 102.0]
    df[cols["anchor"]] = [102.0, 102.0, 102.0]
    df[cols["slow"]] = [101.0, 103.0, 102.0]

    fn = resolve_component("blockers", "counter_candle_blocker").func
    base_mask = fn(df, side="long")
    assert base_mask.tolist() == [True, True, True]
    assert rule_baseline.context_consumption is None

    bundle = ContextBundle.build(spec, df, plan)
    assert bundle.get("htf").state_series().tolist() == ["up", "down", "neutral"]

    gated_aligned = _apply_blocker_context_gate(base_mask, rule=rule_gate_aligned, bundle=bundle, side="long")
    assert gated_aligned.tolist() == [True, False, False]

    gated_aligned_counter = _apply_blocker_context_gate(
        base_mask, rule=rule_gate_aligned_counter, bundle=bundle, side="long"
    )
    assert gated_aligned_counter.tolist() == [True, True, False]

    assert base_mask.tolist() == fn(df, side="long").tolist()


def test_builder_rejects_no_blockers_with_context_consumption() -> None:
    with pytest.raises(ValueError, match="context_consumption is not supported"):
        make_ema_pullback_strategy_spec(
            components=component_stack(
                direction=direction_ema_anchor_stack(),
                blockers=(
                    blocker_rule(
                        NO_BLOCKERS_COMPONENT,
                        instance_id="no_blockers",
                        context_consumption=                        context_consumption(
                            context_ref="htf",
                            policy_id=HTF_REGIME_GATE_POLICY,
                            params=(("allowed_regimes", ["aligned"]),),
                        ),
                    ),
                ),
                trigger=trigger_reclaim_anchor(),
                risk=risk_no_filter(),
            ),
        )


def test_builder_accepts_rsi_blocker_with_context_consumption() -> None:
    from research.strategies.ema_pullback.component_builders import rsi_feature
    from research.strategies.ema_pullback.components.registry import (
        RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT,
    )

    spec = make_ema_pullback_strategy_spec(
        components=component_stack(
            direction=direction_ema_anchor_stack(),
            blockers=(
                blocker_rule(
                    RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT,
                    instance_id="rsi_block",
                    rsi=rsi_feature(timeframe="base", period=14),
                    context_consumption=                    context_consumption(
                        context_ref="htf",
                        policy_id=HTF_REGIME_GATE_POLICY,
                        params=(("allowed_regimes", ["aligned"]),),
                    ),
                ),
            ),
            trigger=trigger_reclaim_anchor(),
            risk=risk_no_filter(),
        ),
    )
    rule = spec.components.blockers[0]
    assert rule.context_consumption is not None
    assert rule.context_consumption.policy.policy_id == HTF_REGIME_GATE_POLICY


def test_loader_rejects_htf_state_gate_policy() -> None:
    instance = {
        "instance_id": "gate",
        "variant": "v",
        "market": {"symbol": "BTCUSDT", "base_timeframe": "1h"},
        "strategy": {
            "trade_sides": ["long"],
            "anchor_stack": {"source": "close", "timeframe": "base", "fast": 100, "anchor": 200, "slow": 1000},
            "direction": {"component_id": "ema_anchor_stack_trend"},
            "setup": {"component_id": "untouched_anchor_setup", "lookback": 50, "active_bars": 3},
            "trigger": {"component_id": "reclaim_anchor"},
            "blockers": [
                {
                    "instance_id": "ccb",
                    "component_id": "counter_candle_blocker",
                    "context_consumption": {
                        "context_ref": "htf",
                        "policy": {
                            "policy_id": "htf_state_gate",
                            "params": {"allowed_states": ["up"]},
                        },
                    },
                }
            ],
            "risk": {"component_id": "no_risk_filter"},
            "contexts": {
                "htf": {
                    "component_id": "htf_context",
                    "timeframe": "4h",
                    "source": "close",
                    "fast_period": 100,
                    "anchor_period": 200,
                    "slow_period": 1000,
                }
            },
            "trade_management": {
                "exit_policy": {
                    "always_on": {
                        "exits": [
                            {
                                "instance_id": "atr_sl",
                                "component_id": "atr_stop_loss",
                                "distance": {"timeframe": "base", "period": 14, "multiplier": 1.5},
                            }
                        ]
                    },
                    "profiles": {
                        "aligned": {"exits": []},
                        "countertrend": {"exits": []},
                        "neutral": {"exits": []},
                    },
                }
            },
        },
    }
    with pytest.raises(EmaPullbackInstanceValidationError, match="htf_state_gate"):
        load_ema_pullback_instance(instance)


def test_loader_rejects_htf_regime_gate_without_allowed_regimes() -> None:
    instance = {
        "instance_id": "regime_gate",
        "variant": "v",
        "market": {"symbol": "BTCUSDT", "base_timeframe": "1h"},
        "strategy": {
            "trade_sides": ["long"],
            "anchor_stack": {"source": "close", "timeframe": "base", "fast": 100, "anchor": 200, "slow": 1000},
            "direction": {"component_id": "ema_anchor_stack_trend"},
            "setup": {"component_id": "untouched_anchor_setup", "lookback": 50, "active_bars": 3},
            "trigger": {"component_id": "reclaim_anchor"},
            "blockers": [
                {
                    "instance_id": "ccb",
                    "component_id": "counter_candle_blocker",
                    "context_consumption": {
                        "context_ref": "htf",
                        "policy": {"policy_id": HTF_REGIME_GATE_POLICY, "params": {}},
                    },
                }
            ],
            "risk": {"component_id": "no_risk_filter"},
            "contexts": {
                "htf": {
                    "component_id": "htf_context",
                    "timeframe": "4h",
                    "source": "close",
                    "fast_period": 100,
                    "anchor_period": 200,
                    "slow_period": 1000,
                }
            },
            "trade_management": {
                "exit_policy": {
                    "always_on": {
                        "exits": [
                            {
                                "instance_id": "atr_sl",
                                "component_id": "atr_stop_loss",
                                "distance": {"timeframe": "base", "period": 14, "multiplier": 1.5},
                            }
                        ]
                    },
                    "profiles": {
                        "aligned": {"exits": []},
                        "countertrend": {"exits": []},
                        "neutral": {"exits": []},
                    },
                }
            },
        },
    }
    with pytest.raises(EmaPullbackInstanceValidationError, match="allowed_regimes"):
        load_ema_pullback_instance(instance)


def test_loader_accepts_rsi_blocker_with_htf_regime_gate() -> None:
    instance = {
        "instance_id": "rsi_regime_gate",
        "variant": "v",
        "market": {"symbol": "BTCUSDT", "base_timeframe": "1h"},
        "strategy": {
            "trade_sides": ["long"],
            "anchor_stack": {"source": "close", "timeframe": "base", "fast": 100, "anchor": 200, "slow": 1000},
            "direction": {"component_id": "ema_anchor_stack_trend"},
            "setup": {"component_id": "untouched_anchor_setup", "lookback": 50, "active_bars": 3},
            "trigger": {"component_id": "reclaim_anchor"},
            "blockers": [
                {
                    "instance_id": "rsi_block",
                    "component_id": "rsi_lookback_extreme_blocker",
                    "timeframe": "base",
                    "period": 14,
                    "context_consumption": {
                        "context_ref": "htf",
                        "policy": {
                            "policy_id": HTF_REGIME_GATE_POLICY,
                            "params": {"allowed_regimes": ["aligned", "neutral"]},
                        },
                    },
                }
            ],
            "risk": {"component_id": "no_risk_filter"},
            "contexts": {
                "htf": {
                    "component_id": "htf_context",
                    "timeframe": "4h",
                    "source": "close",
                    "fast_period": 100,
                    "anchor_period": 200,
                    "slow_period": 1000,
                }
            },
            "trade_management": {
                "exit_policy": {
                    "always_on": {
                        "exits": [
                            {
                                "instance_id": "atr_sl",
                                "component_id": "atr_stop_loss",
                                "distance": {"timeframe": "base", "period": 14, "multiplier": 1.5},
                            }
                        ]
                    },
                    "profiles": {
                        "aligned": {"exits": []},
                        "countertrend": {"exits": []},
                        "neutral": {"exits": []},
                    },
                }
            },
        },
    }
    spec = load_ema_pullback_instance(instance)
    rule = spec.components.blockers[0]
    assert rule.context_consumption is not None
    assert rule.context_consumption.policy.policy_id == HTF_REGIME_GATE_POLICY
    params = dict(rule.context_consumption.policy.params)
    assert list(params["allowed_regimes"]) == ["aligned", "neutral"]


def test_signals_and_exits_require_shared_injected_context_bundle(monkeypatch) -> None:
    pytest.importorskip("pandas")
    import pandas as pd

    build_calls: list[str] = []
    real_build = ContextBundle.build

    def counting_build(spec: object, df: object, plan: object) -> ContextBundle:
        build_calls.append("build")
        return real_build(spec, df, plan)  # type: ignore[arg-type]

    monkeypatch.setattr(ContextBundle, "build", counting_build)

    spec = make_ema_pullback_strategy_spec(
        contexts=htf_strategy_contexts(),
        components=component_stack(
            direction=direction_ema_anchor_stack(),
            blockers=(blocker_counter_candle(),),
            trigger=trigger_reclaim_anchor(),
            risk=risk_no_filter(),
        ),
        enabled_sides=("long",),
    )
    plan = build_feature_plan_from_strategy_spec(spec)
    idx = pd.date_range("2024-01-01", periods=2, freq="h", tz="UTC")
    close = pd.Series([100.0, 101.0], index=idx)
    ohlcv = pd.DataFrame(
        {"close": close, "open": close, "high": close, "low": close, "volume": 1.0},
        index=idx,
    )
    df = add_feature_columns_from_plan(ohlcv, plan)

    bundle = build_context_bundle_for_spec(spec, df, plan)
    assert len(build_calls) == 1

    with pytest.raises(ValueError, match="context_bundle is required"):
        build_signals_from_spec(df, spec, plan)

    build_signals_from_spec(df, spec, plan, context_bundle=bundle)
    build_exit_outputs_from_spec(df, spec, plan, context_bundle=bundle)
    assert len(build_calls) == 1
