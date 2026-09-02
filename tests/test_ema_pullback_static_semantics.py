from __future__ import annotations

import copy

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.static_semantics import (
    check_ema_pullback_static_semantics,
)


def _valid_raw_spec() -> dict[str, object]:
    return {
        "trade_sides": ["long"],
        "components": {
            "direction": "ema_anchor_stack_trend",
            "blockers": [{"component_id": "no_blockers", "instance_id": "blocker-1"}],
            "trigger": {"component_id": "reclaim_anchor"},
            "risk": "no_risk_filter",
        },
        "setups": [{"component_id": "untouched_anchor_setup", "instance_id": "setup-1"}],
        "trade_management": {
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "component_id": "atr_stop_loss",
                            "exit_kind": "stop_loss",
                            "instance_id": "exit-1",
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
    }


def test_valid_raw_spec_passes() -> None:
    check_ema_pullback_static_semantics(_valid_raw_spec())


def test_unsupported_blocker_component_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    spec["components"]["blockers"][0]["component_id"] = "nonexistent"  # type: ignore[index]
    with pytest.raises(InvalidRequestError, match="unsupported blocker component"):
        check_ema_pullback_static_semantics(spec)


def test_unsupported_trigger_component_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    spec["components"]["trigger"]["component_id"] = "nonexistent"  # type: ignore[index]
    with pytest.raises(InvalidRequestError, match="unsupported trigger component"):
        check_ema_pullback_static_semantics(spec)


def test_unsupported_risk_component_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    spec["components"]["risk"] = "nonexistent"  # type: ignore[index]
    with pytest.raises(InvalidRequestError, match="unsupported risk component"):
        check_ema_pullback_static_semantics(spec)


def test_unsupported_setup_component_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    spec["setups"][0]["component_id"] = "nonexistent"  # type: ignore[index]
    with pytest.raises(InvalidRequestError, match="unsupported setup component"):
        check_ema_pullback_static_semantics(spec)


def test_unsupported_exit_component_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    exits = spec["trade_management"]["exit_policy"]["always_on"]["exits"]  # type: ignore[index]
    exits[0]["component_id"] = "nonexistent"
    with pytest.raises(InvalidRequestError, match="unsupported exit component"):
        check_ema_pullback_static_semantics(spec)


def test_unsupported_direction_component_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    spec["components"]["direction"] = "nonexistent"  # type: ignore[index]
    with pytest.raises(InvalidRequestError, match="unsupported direction component"):
        check_ema_pullback_static_semantics(spec)


def test_missing_blocker_instance_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    del spec["components"]["blockers"][0]["instance_id"]  # type: ignore[index]
    with pytest.raises(InvalidRequestError, match="must be a non-empty string"):
        check_ema_pullback_static_semantics(spec)


def test_missing_setup_instance_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    del spec["setups"][0]["instance_id"]  # type: ignore[index]
    with pytest.raises(InvalidRequestError, match="must be a non-empty string"):
        check_ema_pullback_static_semantics(spec)


def test_missing_exit_instance_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    exits = spec["trade_management"]["exit_policy"]["always_on"]["exits"]  # type: ignore[index]
    del exits[0]["instance_id"]
    with pytest.raises(InvalidRequestError, match="must be a non-empty string"):
        check_ema_pullback_static_semantics(spec)


def test_duplicate_blocker_instance_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    spec["components"]["blockers"].append(  # type: ignore[index]
        {"component_id": "no_blockers", "instance_id": "blocker-1"}
    )
    with pytest.raises(InvalidRequestError, match="components.blockers instance_id must be unique"):
        check_ema_pullback_static_semantics(spec)


def test_duplicate_setup_instance_id_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    spec["setups"].append(  # type: ignore[index]
        {"component_id": "untouched_anchor_setup", "instance_id": "setup-1"}
    )
    with pytest.raises(InvalidRequestError, match="setups instance_id must be unique"):
        check_ema_pullback_static_semantics(spec)


def test_duplicate_exit_instance_id_across_groups_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    exit_policy = spec["trade_management"]["exit_policy"]  # type: ignore[index]
    exit_policy["profiles"]["aligned"]["exits"] = [
        {
            "component_id": "atr_stop_loss",
            "exit_kind": "stop_loss",
            "instance_id": "exit-1",
            "distance": {"timeframe": "base", "period": 14, "multiplier": 1.5},
        }
    ]
    with pytest.raises(
        InvalidRequestError, match="trade_management.exit_policy instance_id must be unique"
    ):
        check_ema_pullback_static_semantics(spec)


def test_malformed_trade_sides_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    spec["trade_sides"] = ["sideways"]
    with pytest.raises(InvalidRequestError, match="raw_spec.trade_sides must contain long/short"):
        check_ema_pullback_static_semantics(spec)


def test_non_object_blocker_entry_rejected() -> None:
    spec = copy.deepcopy(_valid_raw_spec())
    spec["components"]["blockers"] = ["not_an_object"]  # type: ignore[index]
    with pytest.raises(InvalidRequestError, match="must be an object"):
        check_ema_pullback_static_semantics(spec)


def test_does_not_require_market_data_argument() -> None:
    # Structural guard: the function signature takes only raw_spec, no
    # FeatureFrame/market-data parameter -- authoring validation cannot
    # accidentally couple to execution-time data.
    import inspect

    signature = inspect.signature(check_ema_pullback_static_semantics)
    assert list(signature.parameters) == ["raw_spec"]
