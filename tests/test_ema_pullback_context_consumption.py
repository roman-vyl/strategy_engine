from __future__ import annotations

from strategy_engine.strategies.ema_pullback.context_consumption import (
    build_context_consumption_evidence,
    resolve_htf_regime,
)
from strategy_engine.strategies.ema_pullback.contexts import ContextBundle, ContextOutput


def bundle() -> ContextBundle:
    return ContextBundle(
        time_ms=(0, 1, 2),
        outputs=(
            ContextOutput(
                context_ref="htf",
                provider={"component_id": "htf_context"},
                state=("up", "down", "neutral"),
                up=(True, False, False),
                down=(False, True, False),
                neutral=(False, False, True),
            ),
        ),
    )


def spec() -> dict[str, object]:
    return {
        "trade_sides": ["long", "short"],
        "components": {
            "blockers": [
                {
                    "instance_id": "gate",
                    "component_id": "counter_candle_blocker",
                    "context_consumption": {
                        "context_ref": "htf",
                        "policy": {
                            "policy_id": "htf_regime_gate",
                            "params": {"allowed_regimes": ["aligned", "neutral"]},
                        },
                    },
                }
            ]
        },
        "setups": [],
        "trade_management": {
            "exit_policy": {
                "context_consumption": {
                    "context_ref": "htf",
                    "policy": {
                        "policy_id": "exit_profile_by_htf_state",
                        "params": {},
                    },
                }
            }
        },
    }


def test_resolve_htf_regime_is_side_relative() -> None:
    assert [resolve_htf_regime(item, "long") for item in ("up", "down", "neutral")] == [
        "aligned",
        "countertrend",
        "neutral",
    ]
    assert [resolve_htf_regime(item, "short") for item in ("up", "down", "neutral")] == [
        "countertrend",
        "aligned",
        "neutral",
    ]


def test_builds_gate_and_exit_profile_evidence() -> None:
    records = build_context_consumption_evidence(spec(), bundle())
    long_gate, short_gate, exit_profiles = records
    assert long_gate.resolved_regime == ("aligned", "countertrend", "neutral")
    assert long_gate.allowed == (True, False, True)
    assert short_gate.resolved_regime == ("countertrend", "aligned", "neutral")
    assert short_gate.allowed == (False, True, True)
    assert exit_profiles.profile_long == ("aligned", "countertrend", "neutral")
    assert exit_profiles.profile_short == ("countertrend", "aligned", "neutral")
