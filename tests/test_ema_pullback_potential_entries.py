from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.exits import ExitPolicyEvaluation
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.potential_entries import (
    PotentialEntry,
    potential_entries_to_wire,
    project_potential_entries,
)
from strategy_engine.strategies.ema_pullback.setups import SideSetupEvaluation
from strategy_engine.strategies.ema_pullback.triggers import (
    SideTriggerEvaluation,
    TriggerMask,
)


def raw_spec(trigger: str = "touch_anchor") -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "components": {"blockers": [], "trigger": {"component_id": trigger}},
        "setups": [],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {"exits": []},
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {},
        },
    }


def frame_and_plan(
    spec: dict[str, object],
    anchors: tuple[str | None, ...] = ("100", "101", "103", "105"),
) -> tuple[FeatureFrame, object]:
    plan = build_feature_plan_from_canonical_spec(spec)
    frame = FeatureFrame(
        market=MarketStream("BTCUSDT.P", "5m"),
        requested_range=TimeRange(0, 1_200_000),
        time_ms=(0, 300_000, 600_000, 900_000),
        series={plan.anchor_columns["anchor"]: anchors},
        validity={},
        plan_hash="plan",
        market_data_hash="market",
    )
    return frame, plan


def exit_policy(
    *,
    stop_long: tuple[float | None, ...] = (1.0, 1.5, 2.0, 2.5),
    stop_short: tuple[float | None, ...] = (1.0, 1.5, 2.0, 2.5),
    take_long: tuple[float | None, ...] = (3.0, 3.5, 4.0, 4.5),
    take_short: tuple[float | None, ...] = (3.0, 3.5, 4.0, 4.5),
) -> ExitPolicyEvaluation:
    text = ("neutral",) * 4
    false = (False,) * 4
    true = (True,) * 4
    none = (None,) * 4
    return ExitPolicyEvaluation(
        context_state=text,
        profile_long=text,
        profile_short=text,
        signal_exit_long=false,
        signal_exit_short=false,
        stop_loss_ratio_long=none,
        stop_loss_ratio_short=none,
        take_profit_ratio_long=none,
        take_profit_ratio_short=none,
        stop_loss_distance_long=stop_long,
        stop_loss_distance_short=stop_short,
        take_profit_distance_long=take_long,
        take_profit_distance_short=take_short,
        stop_ready_long=true,
        stop_ready_short=true,
        signal_by_profile_long={},
        signal_by_profile_short={},
        stop_loss_by_profile={},
        take_profit_by_profile={},
        rule_evidence=(),
    )


def setup(side: str, allowed: tuple[bool, ...] = (True, True, True, True)) -> SideSetupEvaluation:
    return SideSetupEvaluation(side, (), allowed, allowed)


def trigger(
    side: str,
    *,
    component_id: str = "touch_anchor",
    close_ok: tuple[bool, ...] = (True, True, True, True),
    fired: tuple[bool, ...] = (False, False, False, False),
) -> SideTriggerEvaluation:
    trace: dict[str, tuple[object, ...]] = (
        {"close_ok": close_ok} if component_id == "touch_anchor" else {}
    )
    return SideTriggerEvaluation(
        side=side,
        trigger=TriggerMask(component_id, side, fired, trace),
        pre_risk_entry_allowed=fired,
    )


def test_potential_entry_is_minimal_and_immutable() -> None:
    assert [item.name for item in fields(PotentialEntry)] == [
        "side",
        "entry_price",
        "stop_price",
        "take_price",
    ]
    item = PotentialEntry("long", (100.0,), (99.0,), (102.0,))
    with pytest.raises(FrozenInstanceError):
        item.side = "short"  # type: ignore[misc]


def test_touch_anchor_projects_long_and_short_raw_distance_geometry() -> None:
    spec = raw_spec()
    frame, plan = frame_and_plan(spec)
    output = project_potential_entries(
        frame,
        plan,
        (setup("long"), setup("short")),
        (trigger("long"), trigger("short")),
        exit_policy(),
    )

    assert set(output) == {"long", "short"}
    assert output["long"].entry_price == (100.0, 101.0, 103.0, 105.0)
    assert output["long"].stop_price == (99.0, 99.5, 101.0, 102.5)
    assert output["long"].take_price == (103.0, 104.5, 107.0, 109.5)
    assert output["short"].stop_price == (101.0, 102.5, 105.0, 107.5)
    assert output["short"].take_price == (97.0, 97.5, 99.0, 100.5)


def test_projection_changes_bar_by_bar_and_does_not_apply_close_relative_ratios() -> None:
    spec = raw_spec()
    frame, plan = frame_and_plan(spec, ("80", "90", "110", "140"))
    output = project_potential_entries(
        frame,
        plan,
        (setup("long"),),
        (trigger("long"),),
        exit_policy(stop_long=(2.0, 3.0, 5.0, 8.0)),
    )["long"]

    assert output.stop_price == (78.0, 87.0, 105.0, 132.0)
    assert output.take_price == (83.0, 93.5, 114.0, 144.5)


def test_pre_trigger_denial_and_warmup_suppress_the_complete_triple() -> None:
    spec = raw_spec()
    frame, plan = frame_and_plan(spec, (None, "101", "103", "105"))
    output = project_potential_entries(
        frame,
        plan,
        (setup("long", (True, False, True, True)),),
        (trigger("long"),),
        exit_policy(stop_long=(1.0, 1.0, None, 1.0)),
    )["long"]

    assert output.entry_price == (None, None, None, 105.0)
    assert output.stop_price == (None, None, None, 104.0)
    assert output.take_price == (None, None, None, 109.5)


@pytest.mark.parametrize(
    ("anchors", "stops", "takes"),
    [
        (("0", "101", "103", "105"), (1.0, 1.0, 1.0, 1.0), (1.0,) * 4),
        (("-1", "101", "103", "105"), (1.0, 1.0, 1.0, 1.0), (1.0,) * 4),
        (("100", "101", "103", "105"), (0.0, 1.0, 1.0, 1.0), (1.0,) * 4),
        (("100", "101", "103", "105"), (-1.0, 1.0, 1.0, 1.0), (1.0,) * 4),
        (("100", "101", "103", "105"), (1.0,) * 4, (0.0, 1.0, 1.0, 1.0)),
        (("100", "101", "103", "105"), (1.0,) * 4, (-1.0, 1.0, 1.0, 1.0)),
        (("1", "101", "103", "105"), (1.0,) * 4, (1.0,) * 4),
    ],
)
def test_non_positive_source_or_derived_price_suppresses_all_values(
    anchors: tuple[str | None, ...],
    stops: tuple[float | None, ...],
    takes: tuple[float | None, ...],
) -> None:
    spec = raw_spec()
    frame, plan = frame_and_plan(spec, anchors)
    output = project_potential_entries(
        frame,
        plan,
        (setup("long"),),
        (trigger("long"),),
        exit_policy(stop_long=stops, take_long=takes),
    )["long"]
    assert (output.entry_price[0], output.stop_price[0], output.take_price[0]) == (
        None,
        None,
        None,
    )


def test_non_touch_trigger_is_empty_and_touch_includes_only_evaluated_sides() -> None:
    spec = raw_spec("reclaim_anchor")
    frame, plan = frame_and_plan(spec)
    assert project_potential_entries(
        frame,
        plan,
        (setup("long"), setup("short")),
        (
            trigger("long", component_id="reclaim_anchor"),
            trigger("short", component_id="reclaim_anchor"),
        ),
        exit_policy(),
    ) == {}

    touch_spec = raw_spec()
    frame, plan = frame_and_plan(touch_spec)
    output = project_potential_entries(
        frame, plan, (setup("long"),), (trigger("long"),), exit_policy()
    )
    assert set(output) == {"long"}


def test_touch_projection_rejects_missing_close_side_output() -> None:
    spec = raw_spec()
    frame, plan = frame_and_plan(spec)
    malformed = SideTriggerEvaluation(
        side="long",
        trigger=TriggerMask(
            component_id="touch_anchor",
            side="long",
            allowed=(False, False, False, False),
            trace={},
        ),
        pre_risk_entry_allowed=(False, False, False, False),
    )

    with pytest.raises(
        InvalidRequestError,
        match="touch_anchor trigger must expose a bar-aligned boolean close_ok trace",
    ):
        project_potential_entries(
            frame,
            plan,
            (setup("long"),),
            (malformed,),
            exit_policy(),
        )


def test_touch_close_side_precondition_suppresses_marketable_plan() -> None:
    spec = raw_spec()
    frame, plan = frame_and_plan(spec)
    output = project_potential_entries(
        frame,
        plan,
        (setup("long"), setup("short")),
        (
            trigger("long", close_ok=(False, True, True, True)),
            trigger("short", close_ok=(True, False, True, True)),
        ),
        exit_policy(),
    )

    assert output["long"].entry_price[0] is None
    assert output["long"].stop_price[0] is None
    assert output["long"].take_price[0] is None
    assert output["short"].entry_price[1] is None
    assert output["short"].stop_price[1] is None
    assert output["short"].take_price[1] is None
    assert output["long"].entry_price[1:] == (101.0, 103.0, 105.0)
    assert output["short"].entry_price[0] == 100.0
    assert output["short"].entry_price[2:] == (103.0, 105.0)


def test_wire_projection_uses_decimal_text_nulls_and_no_duplicated_metadata() -> None:
    item = PotentialEntry("long", (100.0, None), (99.25, None), (102.5, None))
    wire = potential_entries_to_wire({"long": item})

    assert wire == {
        "long": {
            "entry_price": ["100", None],
            "stop_price": ["99.25", None],
            "take_price": ["102.5", None],
        }
    }
    long_wire = wire["long"]
    assert isinstance(long_wire, dict)
    assert set(long_wire) == {"entry_price", "stop_price", "take_price"}


def test_trigger_firing_state_is_not_an_input_to_projection() -> None:
    spec = raw_spec()
    frame, plan = frame_and_plan(spec)
    not_fired = project_potential_entries(
        frame,
        plan,
        (setup("long"),),
        (trigger("long", fired=(False, False, False, False)),),
        exit_policy(),
    )["long"]
    fired = project_potential_entries(
        frame,
        plan,
        (setup("long"),),
        (trigger("long", fired=(True, True, True, True)),),
        exit_policy(),
    )["long"]

    assert fired == not_fired
    assert all(value is not None for value in fired.entry_price)


def test_non_finite_values_are_suppressed_as_complete_triples() -> None:
    spec = raw_spec()
    frame, plan = frame_and_plan(spec, ("NaN", "101", "103", "105"))
    policy = replace(
        exit_policy(),
        take_profit_distance_long=(float("inf"), 1.0, 1.0, 1.0),
    )
    output = project_potential_entries(
        frame,
        plan,
        (setup("long"),),
        (trigger("long"),),
        policy,
    )["long"]
    assert output.entry_price[0] is None
    assert output.stop_price[0] is None
    assert output.take_price[0] is None
