from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research.experiments.config_loader import load_strategy_config
from research.strategies.ema_pullback.spec import (
    BreakEvenStopParamsSpec,
    LEGACY_EXIT_MANAGEMENT_SHAPE_ERROR,
    LockProfitStopParamsSpec,
    PhaseRuntimeExitParamsSpec,
    TakeProfileSwitchParamsSpec,
    strategy_spec_to_dict,
)
from tests.test_external_config_loader import _bundle, _instance


def _fixture_payload() -> dict[str, object]:
    return _bundle([_instance()])


def _strategy(payload: dict[str, object]) -> dict[str, object]:
    instances = payload["instances"]
    assert isinstance(instances, list)
    instance = instances[0]
    assert isinstance(instance, dict)
    strategy = instance["strategy"]
    assert isinstance(strategy, dict)
    return strategy


def _trade_management(payload: dict[str, object]) -> dict[str, object]:
    trade_management = _strategy(payload)["trade_management"]
    assert isinstance(trade_management, dict)
    return trade_management


def _diagnostic_only_exit_management() -> dict[str, object]:
    return {
        "mode": "diagnostic_only",
        "phase_rules": [
            {
                "rule_id": "to_proven_at_1atr",
                "to_phase": "proven",
                "condition": {
                    "component_id": "mfe_atr",
                    "params": {
                        "threshold": 1.0,
                        "atr": {"timeframe": "base", "period": 14},
                    },
                },
            },
            {
                "rule_id": "to_runner_after_24_bars",
                "to_phase": "runner",
                "condition": {
                    "component_id": "bars_in_trade",
                    "params": {"threshold": 24},
                },
            },
        ],
        "stop_management": [],
        "take_management": [],
        "runtime_exits": [],
    }


def _managed_rule_payload(component_id: str) -> dict[str, object]:
    if component_id == "break_even_stop":
        return {
            "rule_id": "be_after_protected",
            "component_id": "break_even_stop",
            "activate_when": {"phase_at_least": "protected"},
            "params": {"buffer_type": "none", "buffer": 0},
        }
    if component_id == "lock_profit_stop":
        return {
            "rule_id": "lock_profit_after_protected",
            "component_id": "lock_profit_stop",
            "activate_when": {"phase_at_least": "protected"},
            "params": {"lock_atr": 0.5, "atr_period": 14},
        }
    if component_id == "take_profile_switch":
        return {
            "rule_id": "tp_switch",
            "component_id": "take_profile_switch",
            "activate_when": {"phase_at_least": "runner"},
            "params": {"action": "keep_initial"},
        }
    return {
        "rule_id": "exit_on_exhaustion",
        "component_id": "phase_runtime_exit",
        "role": "exit_management.runtime_exit",
        "activate_when": {"phase_at_least": "exhaustion"},
        "exit_kind": "market_close",
        "params": {"exit_price": "close"},
    }


def _managed_exit_management(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "mode": "managed",
        "phase_rules": [],
        "stop_management": [],
        "take_management": [],
        "runtime_exits": [],
    }
    base.update(overrides)
    return base


def test_old_config_without_exit_management_uses_empty_contract() -> None:
    loaded = load_strategy_config(_fixture_payload())
    exit_management = loaded.specs[0].trade_management.exit_management

    assert exit_management.mode is None
    assert exit_management.phase_rules == ()
    assert exit_management.stop_management == ()
    assert exit_management.take_management == ()
    assert exit_management.runtime_exits == ()


@pytest.mark.parametrize(
    "legacy_block",
    [
        {"always_on": {"rules": []}},
        {
            "profiles": {
                "aligned": {"rules": []},
                "countertrend": {"rules": []},
                "neutral": {"rules": []},
            }
        },
        {
            "always_on": {
                "rules": [
                    {
                        "instance_id": "be_ao",
                        "component_id": "break_even_stop",
                        "trigger_r": 1.0,
                    }
                ]
            },
            "profiles": {
                "aligned": {"rules": []},
                "countertrend": {"rules": []},
                "neutral": {"rules": []},
            },
        },
    ],
)
def test_legacy_exit_management_shape_rejected_by_key_presence(
    legacy_block: dict[str, object],
) -> None:
    payload = _fixture_payload()
    exit_management = _managed_exit_management()
    exit_management.update(legacy_block)
    _trade_management(payload)["exit_management"] = exit_management

    with pytest.raises(ValueError, match=LEGACY_EXIT_MANAGEMENT_SHAPE_ERROR):
        load_strategy_config(payload)


def test_diagnostic_only_exit_management_config_loads() -> None:
    payload = _fixture_payload()
    _trade_management(payload)["exit_management"] = _diagnostic_only_exit_management()

    loaded = load_strategy_config(payload)
    exit_management = loaded.specs[0].trade_management.exit_management

    assert exit_management.mode == "diagnostic_only"
    assert [rule.rule_id for rule in exit_management.phase_rules] == [
        "to_proven_at_1atr",
        "to_runner_after_24_bars",
    ]
    from research.strategies.ema_pullback.phase_rule_conditions.params import (
        MfeAtrConditionParams,
    )

    assert exit_management.phase_rules[0].condition.component_id == "mfe_atr"
    params = exit_management.phase_rules[0].condition.params
    assert isinstance(params, MfeAtrConditionParams)
    assert params.atr.period == 14


def test_diagnostic_only_rejects_non_empty_stop_management() -> None:
    payload = _fixture_payload()
    exit_management = _diagnostic_only_exit_management()
    exit_management["stop_management"] = [_managed_rule_payload("break_even_stop")]
    _trade_management(payload)["exit_management"] = exit_management

    with pytest.raises(ValueError, match="stop_management is not allowed in diagnostic-only mode"):
        load_strategy_config(payload)


def test_diagnostic_only_rejects_non_empty_take_management() -> None:
    payload = _fixture_payload()
    exit_management = _diagnostic_only_exit_management()
    exit_management["take_management"] = [
        {
            "rule_id": "disable_fixed_tp_runner",
            "component_id": "take_profile_switch",
            "activate_when": {"phase_at_least": "runner"},
            "params": {"action": "disable_fixed_tp"},
        }
    ]
    _trade_management(payload)["exit_management"] = exit_management

    with pytest.raises(ValueError, match="take_management is not allowed in diagnostic-only mode"):
        load_strategy_config(payload)


def test_diagnostic_only_rejects_non_empty_runtime_exits() -> None:
    payload = _fixture_payload()
    exit_management = _diagnostic_only_exit_management()
    exit_management["runtime_exits"] = [_managed_rule_payload("phase_runtime_exit")]
    _trade_management(payload)["exit_management"] = exit_management

    with pytest.raises(ValueError, match="runtime_exits is not allowed in diagnostic-only mode"):
        load_strategy_config(payload)


def test_diagnostic_only_rejects_phase_rules_that_move_backwards() -> None:
    payload = _fixture_payload()
    exit_management = _diagnostic_only_exit_management()
    exit_management["phase_rules"] = [
        {
            "rule_id": "to_runner_at_2_5atr",
            "to_phase": "runner",
            "condition": {
                "component_id": "mfe_pct",
                "params": {"threshold": 0.025},
            },
        },
        {
            "rule_id": "to_protected_at_1_5atr",
            "to_phase": "protected",
            "condition": {
                "component_id": "mfe_pct",
                "params": {"threshold": 0.015},
            },
        },
    ]
    _trade_management(payload)["exit_management"] = exit_management

    with pytest.raises(ValueError, match="phase_rules must be ordered"):
        load_strategy_config(payload)


def test_default_exit_management_wire_shape_omits_new_empty_fields() -> None:
    loaded = load_strategy_config(_fixture_payload())

    serialized = strategy_spec_to_dict(loaded.specs[0])
    exit_management = serialized["trade_management"]["exit_management"]

    assert "mode" not in exit_management
    assert "phase_rules" not in exit_management
    assert "stop_management" not in exit_management
    assert "take_management" not in exit_management
    assert "runtime_exits" not in exit_management


def test_diagnostic_only_wire_shape_keeps_phase_rules() -> None:
    payload = _fixture_payload()
    _trade_management(payload)["exit_management"] = copy.deepcopy(
        _diagnostic_only_exit_management()
    )
    loaded = load_strategy_config(payload)

    serialized = strategy_spec_to_dict(loaded.specs[0])
    exit_management = serialized["trade_management"]["exit_management"]

    assert exit_management["mode"] == "diagnostic_only"
    assert exit_management["phase_rules"][0]["condition"]["component_id"] == "mfe_atr"


def test_managed_empty_arrays_fixture_loads() -> None:
    payload = _fixture_payload()
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        phase_rules=[
            {
                "rule_id": "to_proven_at_1atr",
                "to_phase": "proven",
                "condition": {
                    "component_id": "mfe_atr",
                    "params": {
                        "threshold": 1.0,
                        "atr": {"timeframe": "base", "period": 14},
                    },
                },
            }
        ],
    )
    loaded = load_strategy_config(payload)
    exit_management = loaded.specs[0].trade_management.exit_management

    assert exit_management.mode == "managed"
    assert exit_management.stop_management == ()
    assert exit_management.take_management == ()
    assert exit_management.runtime_exits == ()
    assert exit_management.phase_rules[0].rule_id == "to_proven_at_1atr"


def test_managed_component_pack_fixture_round_trips() -> None:
    payload = _fixture_payload()
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        phase_rules=[],
        stop_management=[
            {
                "rule_id": "be_after_protected",
                "component_id": "break_even_stop",
                "activate_when": {"phase_at_least": "protected"},
                "params": {"buffer_type": "atr", "buffer_atr": 0.1, "atr_period": 14},
            },
            {
                "rule_id": "lock_profit_after_protected",
                "component_id": "lock_profit_stop",
                "activate_when": {"phase_at_least": "protected"},
                "params": {"lock_atr": 0.5, "atr_period": 14},
            },
        ],
        take_management=[
            {
                "rule_id": "tp_switch",
                "component_id": "take_profile_switch",
                "activate_when": {"phase_at_least": "runner"},
                "params": {"action": "disable_initial_tp"},
            }
        ],
        runtime_exits=[_managed_rule_payload("phase_runtime_exit")],
    )
    loaded = load_strategy_config(payload)
    exit_management = loaded.specs[0].trade_management.exit_management

    assert exit_management.mode == "managed"
    assert len(exit_management.stop_management) == 2
    assert exit_management.stop_management[0].component_id == "break_even_stop"
    assert isinstance(exit_management.stop_management[0].params, BreakEvenStopParamsSpec)
    assert exit_management.stop_management[0].params.buffer_type == "atr"
    assert exit_management.stop_management[1].component_id == "lock_profit_stop"
    assert isinstance(exit_management.stop_management[1].params, LockProfitStopParamsSpec)
    assert exit_management.stop_management[1].params.lock_atr == 0.5

    assert len(exit_management.take_management) == 1
    assert exit_management.take_management[0].component_id == "take_profile_switch"
    assert isinstance(exit_management.take_management[0].params, TakeProfileSwitchParamsSpec)
    assert exit_management.take_management[0].params.action == "disable_initial_tp"

    assert len(exit_management.runtime_exits) == 1
    assert exit_management.runtime_exits[0].component_id == "phase_runtime_exit"
    assert isinstance(exit_management.runtime_exits[0].params, PhaseRuntimeExitParamsSpec)
    assert exit_management.runtime_exits[0].params.exit_price == "close"

    serialized = strategy_spec_to_dict(loaded.specs[0])
    wire = serialized["trade_management"]["exit_management"]
    assert wire["mode"] == "managed"
    assert wire["stop_management"][1]["params"]["lock_atr"] == 0.5
    assert wire["runtime_exits"][0]["params"]["exit_price"] == "close"


def test_managed_rejects_unknown_stop_component_id() -> None:
    payload = _fixture_payload()
    rule = _managed_rule_payload("break_even_stop")
    rule["component_id"] = "ema_trailing_stop"
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        stop_management=[rule]
    )

    with pytest.raises(ValueError, match="component_id must be one of"):
        load_strategy_config(payload)


def test_managed_rejects_unknown_take_profile_switch_action() -> None:
    payload = _fixture_payload()
    rule = _managed_rule_payload("take_profile_switch")
    assert isinstance(rule["params"], dict)
    rule["params"]["action"] = "unknown_action"
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        take_management=[rule]
    )

    with pytest.raises(ValueError, match="params.action must be one of"):
        load_strategy_config(payload)


def test_managed_rejects_phase_runtime_exit_trigger() -> None:
    payload = _fixture_payload()
    rule = _managed_rule_payload("phase_runtime_exit")
    rule["trigger"] = {"component_id": "exhaustion_pattern", "params": {}}
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        runtime_exits=[rule]
    )

    with pytest.raises(ValueError, match="must not include trigger"):
        load_strategy_config(payload)


def test_managed_rejects_phase_runtime_exit_non_close_price() -> None:
    payload = _fixture_payload()
    rule = _managed_rule_payload("phase_runtime_exit")
    assert isinstance(rule["params"], dict)
    rule["params"]["exit_price"] = "open"
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        runtime_exits=[rule]
    )

    with pytest.raises(ValueError, match=r"params\.exit_price must be one of:.*got 'open'"):
        load_strategy_config(payload)


def test_managed_rejects_lock_profit_stop_missing_lock_atr() -> None:
    payload = _fixture_payload()
    rule = _managed_rule_payload("lock_profit_stop")
    assert isinstance(rule["params"], dict)
    rule["params"].pop("lock_atr")
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        stop_management=[rule]
    )

    with pytest.raises(ValueError, match="lock_atr is required"):
        load_strategy_config(payload)


def test_managed_rejects_lock_profit_stop_invalid_lock_atr() -> None:
    payload = _fixture_payload()
    rule = _managed_rule_payload("lock_profit_stop")
    assert isinstance(rule["params"], dict)
    rule["params"]["lock_atr"] = 0
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        stop_management=[rule]
    )

    with pytest.raises(ValueError, match="lock_atr must be a finite number > 0"):
        load_strategy_config(payload)


@pytest.mark.parametrize("lock_atr", [float("nan"), float("inf"), float("-inf")])
def test_managed_rejects_lock_profit_stop_non_finite_lock_atr(lock_atr: float) -> None:
    payload = _fixture_payload()
    rule = _managed_rule_payload("lock_profit_stop")
    assert isinstance(rule["params"], dict)
    rule["params"]["lock_atr"] = lock_atr
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        stop_management=[rule]
    )

    with pytest.raises(ValueError, match="lock_atr must be a finite number > 0"):
        load_strategy_config(payload)


def test_managed_rejects_invalid_phase_at_least_typo() -> None:
    payload = _fixture_payload()
    rule = _managed_rule_payload("break_even_stop")
    rule["activate_when"] = {"phase_at_least": "protcted"}
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        stop_management=[rule]
    )

    with pytest.raises(
        ValueError,
        match=r"activate_when\.phase_at_least must be one of:.*got 'protcted'",
    ):
        load_strategy_config(payload)


def test_managed_rejects_duplicate_rule_id_across_management_arrays() -> None:
    payload = _fixture_payload()
    stop_rule = _managed_rule_payload("break_even_stop")
    take_rule = _managed_rule_payload("take_profile_switch")
    take_rule["rule_id"] = stop_rule["rule_id"]
    _trade_management(payload)["exit_management"] = _managed_exit_management(
        stop_management=[stop_rule],
        take_management=[take_rule],
    )

    with pytest.raises(
        ValueError,
        match="management rule_id must be unique across stop_management, take_management, and runtime_exits",
    ):
        load_strategy_config(payload)


def test_legacy_shape_rejected_without_mode() -> None:
    payload = _fixture_payload()
    _trade_management(payload)["exit_management"] = {"always_on": {"rules": []}}

    with pytest.raises(ValueError, match=LEGACY_EXIT_MANAGEMENT_SHAPE_ERROR):
        load_strategy_config(payload)
