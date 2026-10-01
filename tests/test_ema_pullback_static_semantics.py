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


# -- frozen partial take ladder (OpenSpec frozen-partial-take-ladder-v1) ------


def _tp(instance_id: str = "tp-final") -> dict[str, object]:
    return {
        "component_id": "atr_take_profit",
        "exit_kind": "take_profit",
        "instance_id": instance_id,
        "distance": {"timeframe": "base", "period": 14, "multiplier": 8.0},
    }


def _pct_leg(instance_id: str, fraction: object, pct: object = 0.01) -> dict[str, object]:
    return {
        "component_id": "pct_partial_take",
        "exit_kind": "partial_take",
        "instance_id": instance_id,
        "pct": pct,
        "fraction_of_initial": fraction,
    }


def _atr_leg(instance_id: str, fraction: object, multiplier: object = 2.0) -> dict[str, object]:
    return {
        "component_id": "atr_partial_take",
        "exit_kind": "partial_take",
        "instance_id": instance_id,
        "distance": {"timeframe": "base", "period": 14, "multiplier": multiplier},
        "fraction_of_initial": fraction,
    }


def _ladder_spec(
    always_on: list[dict[str, object]], **profiles: list[dict[str, object]]
) -> dict[str, object]:
    spec = copy.deepcopy(_valid_raw_spec())
    policy = spec["trade_management"]["exit_policy"]  # type: ignore[index]
    policy["always_on"]["exits"].extend(always_on)
    for name, rules in profiles.items():
        policy["profiles"][name]["exits"] = rules
    return spec


def test_partial_take_ladder_passes() -> None:
    check_ema_pullback_static_semantics(
        _ladder_spec([_tp(), _pct_leg("pt-1", 0.25), _atr_leg("pt-2", "0.25")])
    )


def test_partial_take_beyond_final_take_passes() -> None:
    # Final at +8% (pct-equivalent) and a leg at +10%: never compared.
    final = {
        "component_id": "constant_usd_take_profit",
        "exit_kind": "take_profit",
        "instance_id": "tp-usd",
        "usd_distance": 8,
    }
    check_ema_pullback_static_semantics(_ladder_spec([final, _pct_leg("pt-far", 0.25, 0.10)]))


def test_partial_take_fraction_sum_below_one_passes() -> None:
    check_ema_pullback_static_semantics(
        _ladder_spec([_tp(), _pct_leg("a", 0.1), _pct_leg("b", 0.2), _pct_leg("c", 0.6)])
    )


@pytest.mark.parametrize("fraction", [0, 1, 1.2, -0.1, "nan", True, None, "abc"])
def test_partial_take_invalid_fraction_rejected(fraction: object) -> None:
    with pytest.raises(InvalidRequestError, match="fraction_of_initial"):
        check_ema_pullback_static_semantics(_ladder_spec([_tp(), _pct_leg("pt", fraction)]))


def test_partial_take_fractions_sum_to_one_rejected() -> None:
    spec = _ladder_spec([_tp(), _pct_leg("a", 0.1), _pct_leg("b", 0.2), _pct_leg("c", 0.7)])
    with pytest.raises(InvalidRequestError, match="sum below 1"):
        check_ema_pullback_static_semantics(spec)


def test_partial_take_fractions_sum_across_always_on_and_profile_rejected() -> None:
    spec = _ladder_spec([_tp(), _pct_leg("a", 0.5)], aligned=[_pct_leg("b", 0.5)])
    with pytest.raises(InvalidRequestError, match="sum below 1") as excinfo:
        check_ema_pullback_static_semantics(spec)
    assert excinfo.value.details.get("profile") == "aligned"


def test_partial_take_without_final_take_rejected() -> None:
    with pytest.raises(InvalidRequestError, match="require a take_profit"):
        check_ema_pullback_static_semantics(_ladder_spec([_pct_leg("pt", 0.25)]))


def test_partial_take_final_take_in_another_profile_only_rejected() -> None:
    spec = _ladder_spec([_pct_leg("pt", 0.25)], aligned=[_tp()])
    with pytest.raises(InvalidRequestError, match="require a take_profit") as excinfo:
        check_ema_pullback_static_semantics(spec)
    assert excinfo.value.details.get("profile") == "countertrend"


@pytest.mark.parametrize("pct", [0, -0.01, "nan", None])
def test_partial_take_non_positive_pct_rejected(pct: object) -> None:
    with pytest.raises(InvalidRequestError, match="pct"):
        check_ema_pullback_static_semantics(_ladder_spec([_tp(), _pct_leg("pt", 0.25, pct)]))


@pytest.mark.parametrize("multiplier", [0, -2.0, None])
def test_partial_take_non_positive_multiplier_rejected(multiplier: object) -> None:
    with pytest.raises(InvalidRequestError, match="multiplier"):
        check_ema_pullback_static_semantics(
            _ladder_spec([_tp(), _atr_leg("pt", 0.25, multiplier)])
        )


def test_partial_take_component_with_take_profit_kind_rejected() -> None:
    leg = _atr_leg("pt", 0.25)
    leg["exit_kind"] = "take_profit"
    with pytest.raises(InvalidRequestError, match="exit_kind"):
        check_ema_pullback_static_semantics(_ladder_spec([_tp(), leg]))


def test_take_profit_component_with_partial_take_kind_rejected() -> None:
    final = _tp()
    final["exit_kind"] = "partial_take"
    with pytest.raises(InvalidRequestError, match="exit_kind"):
        check_ema_pullback_static_semantics(_ladder_spec([final]))


def test_partial_take_duplicate_instance_id_rejected() -> None:
    spec = _ladder_spec([_tp(), _pct_leg("dup", 0.25)], neutral=[_pct_leg("dup", 0.25)])
    with pytest.raises(InvalidRequestError, match="instance_id must be unique"):
        check_ema_pullback_static_semantics(spec)
