from __future__ import annotations

from strategy_engine.strategies.ema_pullback import build_feature_plan_from_canonical_spec


def canonical_spec() -> dict[str, object]:
    return {
        "variant": "fixture",
        "symbol": "BTCUSDT.P",
        "base_timeframe": "5m",
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 20},
            "anchor": {"source": "close", "timeframe": "base", "period": 50},
            "slow": {"source": "close", "timeframe": "base", "period": 200},
        },
        "components": {
            "direction": "ema_anchor_stack_trend",
            "blockers": [
                {
                    "instance_id": "rsi-block",
                    "component_id": "rsi_lookback_extreme_blocker",
                    "rsi": {"timeframe": "1h", "period": 14},
                },
                {
                    "instance_id": "trend-block",
                    "component_id": "trend_strength_episode_blocker",
                    "trend_strength": {"timeframe": "base", "adx_period": 14},
                },
            ],
            "trigger": {"component_id": "reclaim_anchor"},
            "risk": "no_risk_filter",
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "setups": [
            {
                "instance_id": "width",
                "component_id": "anchor_stack_width_setup",
                "params": {"atr_timeframe": "1h", "atr_period": 10},
            },
            {
                "instance_id": "bounce",
                "component_id": "ema_bounce_counter_setup",
                "params": {},
            },
        ],
        "contexts": {
            "htf": {
                "component_id": "htf_context",
                "timeframe": "4h",
                "source": "close",
                "fast_period": 20,
                "anchor_period": 50,
                "slow_period": 200,
            }
        },
        "trade_management": {
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "sl",
                            "component_id": "atr_stop_loss",
                            "exit_kind": "stop_loss",
                            "distance": {"timeframe": "base", "period": 14, "multiplier": 1.5},
                        },
                        {
                            "instance_id": "rsi-exit",
                            "component_id": "rsi_signal_exit",
                            "exit_kind": "signal",
                            "rsi": {"timeframe": "1h", "period": 14},
                        },
                    ]
                },
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {
                "mode": "managed",
                "phase_rules": [
                    {
                        "rule_id": "phase-atr",
                        "to_phase": "proven",
                        "condition": {
                            "component_id": "mfe_atr",
                            "params": {"atr": {"timeframe": "base", "period": 21}},
                        },
                    }
                ],
                "runtime_exits": [
                    {
                        "rule_id": "runtime-ema",
                        "component_id": "ema_cross_loss_exit",
                        "params": {
                            "fast_ema": {"source": "close", "timeframe": "1h", "period": 9},
                            "slow_ema": {"source": "close", "timeframe": "1h", "period": 21},
                        },
                    }
                ],
            },
        },
    }


def test_builds_ordered_deduplicated_indicator_plan_and_mappings() -> None:
    plan = build_feature_plan_from_canonical_spec(canonical_spec())
    ids = [feature.output_id for feature in plan.indicator_plan.features]
    assert ids[:3] == ["ema_close_base_20", "ema_close_base_50", "ema_close_base_200"]
    assert ids.count("rsi_close_1h_14") == 1
    assert "atr_close_base_14_x1_5" in ids
    assert plan.anchor_columns == {
        "fast": "ema_close_base_20",
        "anchor": "ema_close_base_50",
        "slow": "ema_close_base_200",
    }
    assert plan.exit_distance_columns["sl"] == "atr_close_base_14_x1_5"
    assert plan.exit_distance_columns["stop_loss"] == "atr_close_base_14_x1_5"
    assert plan.setup_columns_by_instance_id["width"]["atr"] == "atr_close_1h_10"
    assert plan.htf_context_columns_by_ref["htf"]["anchor"] == "ema_close_4h_50"
    assert plan.adx_dmi_columns[("base", 14)]["adx"] == "adx_close_base_14"
    assert plan.ema_columns[("1h", 9)] == "ema_close_1h_9"


def test_wire_format_uses_stable_string_keys() -> None:
    wire = build_feature_plan_from_canonical_spec(canonical_spec()).to_wire()
    assert wire["rsi_columns"] == {"1h:14": "rsi_close_1h_14"}
    assert "base:14" in wire["adx_dmi_columns"]
    assert isinstance(wire["plan_hash"], str)
