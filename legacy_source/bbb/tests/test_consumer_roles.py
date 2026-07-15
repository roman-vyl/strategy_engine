"""Consumer role registry and runtime exit validation."""

from __future__ import annotations

import pytest

from research.experiments.config_loader import load_strategy_config
from research.strategies.ema_pullback.consumer_roles import (
    CONSUMER_ROLE_REGISTRY,
    validate_consumer_role,
)
from research.strategies.ema_pullback.spec import RuntimeExitRuleSpec
from research_api.services.component_catalog import get_component_catalog
from tests.test_exit_management_contracts import (
    _fixture_payload,
    _managed_exit_management,
    _managed_rule_payload,
    _trade_management,
)


def test_registry_rejects_atr_stop_loss_in_runtime_exits_role() -> None:
    with pytest.raises(ValueError, match="not allowed in role"):
        validate_consumer_role(
            component_id="atr_stop_loss",
            role="exit_management.runtime_exit",
        )


def test_rsi_allowed_in_exit_policy_and_runtime_roles() -> None:
    validate_consumer_role(
        component_id="rsi_signal_exit",
        role="exit_policy.signal_exit",
    )
    validate_consumer_role(
        component_id="rsi_signal_exit",
        role="exit_management.runtime_exit",
    )


def test_registry_params_schema_ref_matches_component_id() -> None:
    for component_id, meta in CONSUMER_ROLE_REGISTRY.items():
        assert meta.params_schema_ref == component_id


def test_catalog_parity_for_allowed_roles() -> None:
    catalog = get_component_catalog(family="ema_pullback")
    by_id = {item.component_id: item for item in catalog.components}
    for component_id, meta in CONSUMER_ROLE_REGISTRY.items():
        if component_id not in by_id:
            continue
        assert set(by_id[component_id].allowed_roles) == set(meta.allowed_roles)


def test_runtime_exit_rejects_exit_kind_signal() -> None:
    payload = _fixture_payload()
    trade_management = _trade_management(payload)
    trade_management["exit_management"] = _managed_exit_management(
        runtime_exits=[
            {
                "rule_id": "runner_rsi",
                "component_id": "rsi_signal_exit",
                "role": "exit_management.runtime_exit",
                "activate_when": {"phase_at_least": "runner"},
                "exit_kind": "signal",
                "params": {
                    "rsi": {"timeframe": "base", "period": 14},
                    "long_exit_above": 90.0,
                    "short_exit_below": 10.0,
                },
            }
        ],
    )
    with pytest.raises(Exception, match="exit_kind"):
        load_strategy_config(payload)


def test_runtime_rsi_validates_with_activate_when() -> None:
    payload = _fixture_payload()
    trade_management = _trade_management(payload)
    trade_management["exit_management"] = _managed_exit_management(
        runtime_exits=[
            {
                "rule_id": "runner_rsi",
                "component_id": "rsi_signal_exit",
                "role": "exit_management.runtime_exit",
                "activate_when": {"phase_at_least": "runner"},
                "exit_kind": "take_profit",
                "params": {
                    "rsi": {"timeframe": "base", "period": 14},
                    "long_exit_above": 90.0,
                    "short_exit_below": 10.0,
                },
            }
        ],
    )
    loaded = load_strategy_config(payload)
    rule = loaded.specs[0].trade_management.exit_management.runtime_exits[0]
    assert isinstance(rule, RuntimeExitRuleSpec)
    assert rule.component_id == "rsi_signal_exit"
    assert rule.exit_kind == "take_profit"


def test_runtime_rejects_atr_stop_loss_component() -> None:
    payload = _fixture_payload()
    trade_management = _trade_management(payload)
    trade_management["exit_management"] = _managed_exit_management(
        runtime_exits=[
            {
                "rule_id": "bad_sl",
                "component_id": "atr_stop_loss",
                "role": "exit_management.runtime_exit",
                "activate_when": {"phase_at_least": "runner"},
                "exit_kind": "protective_exit",
                "params": {
                    "distance": {
                        "timeframe": "base",
                        "period": 14,
                        "multiplier": 4.0,
                    }
                },
            }
        ],
    )
    with pytest.raises(Exception, match="component_id must be one of"):
        load_strategy_config(payload)


def test_smoke_runner_rsi_ema_runtime_config_loads() -> None:
    import json
    from pathlib import Path

    path = Path(
        "research/experiments/specs/smoke/"
        "exit_management_runner_rsi_ema_runtime_smoke.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    loaded = load_strategy_config(payload)
    em = loaded.specs[0].trade_management.exit_management
    assert em.mode == "managed"
    assert len(em.runtime_exits) == 2
    assert {rule.component_id for rule in em.runtime_exits} == {
        "rsi_signal_exit",
        "ema_cross_loss_exit",
    }


def test_phase_runtime_exit_still_valid() -> None:
    payload = _fixture_payload()
    trade_management = _trade_management(payload)
    trade_management["exit_management"] = _managed_exit_management(
        runtime_exits=[_managed_rule_payload("phase_runtime_exit")],
    )
    loaded = load_strategy_config(payload)
    assert (
        loaded.specs[0].trade_management.exit_management.runtime_exits[0].component_id
        == "phase_runtime_exit"
    )
