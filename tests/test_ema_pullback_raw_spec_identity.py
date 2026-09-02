from __future__ import annotations

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    require_non_empty_instance_id,
    require_unique_instance_ids,
    resolve_blocker_identity,
    resolve_direction_component_id,
    resolve_enabled_sides,
    resolve_exit_rule_groups,
    resolve_risk_component_id,
    resolve_setup_identity,
    resolve_trigger_rule,
)


def test_require_non_empty_instance_id_accepts_non_empty_string() -> None:
    assert require_non_empty_instance_id("x", "path") == "x"


@pytest.mark.parametrize("value", [None, "", 0, {}])
def test_require_non_empty_instance_id_rejects_invalid(value: object) -> None:
    with pytest.raises(InvalidRequestError, match="path must be a non-empty string"):
        require_non_empty_instance_id(value, "path")


def test_require_unique_instance_ids_accepts_unique() -> None:
    require_unique_instance_ids("scope", (("a", "p0"), ("b", "p1")))


def test_require_unique_instance_ids_rejects_duplicate() -> None:
    with pytest.raises(InvalidRequestError, match="scope instance_id must be unique"):
        require_unique_instance_ids("scope", (("a", "p0"), ("a", "p1")))


def test_require_unique_instance_ids_rejects_empty_before_duplicate_check() -> None:
    with pytest.raises(InvalidRequestError, match="p0 must be a non-empty string"):
        require_unique_instance_ids("scope", ((None, "p0"), ("a", "p1")))


def test_resolve_blocker_identity_defaults_instance_id_to_component_id() -> None:
    assert resolve_blocker_identity({"component_id": "no_blockers"}) == (
        "no_blockers",
        "no_blockers",
    )


def test_resolve_setup_identity_defaults_instance_id_to_component_id() -> None:
    assert resolve_setup_identity({"component_id": "untouched_anchor_setup"}) == (
        "untouched_anchor_setup",
        "untouched_anchor_setup",
    )


def test_resolve_direction_component_id_defaults() -> None:
    assert resolve_direction_component_id({}) == "ema_anchor_stack_trend"


def test_resolve_trigger_rule_defaults() -> None:
    assert resolve_trigger_rule({})["component_id"] == "reclaim_anchor"


def test_resolve_risk_component_id_defaults() -> None:
    assert resolve_risk_component_id({}) == "no_risk_filter"


def test_resolve_enabled_sides_defaults_to_long() -> None:
    assert resolve_enabled_sides({}) == ("long",)


def test_resolve_enabled_sides_rejects_unknown_side() -> None:
    with pytest.raises(InvalidRequestError, match="raw_spec.trade_sides must contain long/short"):
        resolve_enabled_sides({"trade_sides": ["sideways"]})


def test_resolve_exit_rule_groups_flat_across_groups() -> None:
    raw_spec = {
        "trade_management": {
            "exit_policy": {
                "always_on": {"exits": [{"instance_id": "a"}]},
                "profiles": {
                    "aligned": {"exits": [{"instance_id": "b"}]},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            }
        }
    }
    groups = resolve_exit_rule_groups(raw_spec)
    assert [rule["instance_id"] for rule in groups["always_on"]] == ["a"]
    assert [rule["instance_id"] for rule in groups["aligned"]] == ["b"]
    assert groups["countertrend"] == ()
    assert groups["neutral"] == ()


def test_resolve_exit_rule_groups_defaults_missing_exits_key_to_empty() -> None:
    groups = resolve_exit_rule_groups({})
    assert groups == {"always_on": (), "aligned": (), "countertrend": (), "neutral": ()}
