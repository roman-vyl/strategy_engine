"""Unit tests for the I1 pure builder
(`build_historical_execution_projection`) -- I1 gate per the Master
Plan: executable-entry selection correctness, locked-profile-at-entry
capture, per-profile signal-exit candidate correctness, attribution
population, deterministic multi-rule tie-break.

Constructs `ExitPolicyEvaluation`/`SideEntryEvaluation` directly rather
than driving the full strategy pipeline -- this module's tests are
white-box, matching `test_ema_pullback_exits.py`'s existing convention
of testing internal series construction directly. A lightweight
duck-typed fake stands in for `EmaPullbackEvaluation` (only `.entries`/
`.exit_policy` are read by the builder; `tests/` is not mypy-checked
per the Makefile).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.strategies.ema_pullback.exits import ExitPolicyEvaluation, ExitRuleEvidence
from strategy_engine.strategies.ema_pullback.risk import RiskMask, SideEntryEvaluation
from strategy_engine.strategies.historical_execution_projection import (
    build_historical_execution_projection,
)

_MARKET = MarketStream(ticker="BTCUSDT.P", base_timeframe="5m")
_RANGE = TimeRange(from_ms=0, to_ms=300_000 * 4)


def _entries(side: str, allowed: tuple[bool, ...]) -> SideEntryEvaluation:
    return SideEntryEvaluation(
        side=side,
        risk=RiskMask(component_id="no_risk_filter", side=side, allowed=allowed),
        entry_allowed=allowed,
    )


def _exit_policy(
    *,
    bar_count: int,
    profile_long: tuple[str, ...] | None = None,
    profile_short: tuple[str, ...] | None = None,
    stop_ready_long: tuple[bool, ...] | None = None,
    stop_ready_short: tuple[bool, ...] | None = None,
    sl_long: tuple[float | None, ...] | None = None,
    sl_short: tuple[float | None, ...] | None = None,
    tp_long: tuple[float | None, ...] | None = None,
    tp_short: tuple[float | None, ...] | None = None,
    signal_long: dict[str, tuple[bool, ...]] | None = None,
    signal_short: dict[str, tuple[bool, ...]] | None = None,
    rule_evidence: tuple[ExitRuleEvidence, ...] = (),
) -> ExitPolicyEvaluation:
    neutral = tuple("neutral" for _ in range(bar_count))
    false = tuple(False for _ in range(bar_count))
    none = tuple(None for _ in range(bar_count))
    empty_profiles = {"aligned": false, "countertrend": false, "neutral": false}
    return ExitPolicyEvaluation(
        context_state=neutral,
        profile_long=profile_long or neutral,
        profile_short=profile_short or neutral,
        signal_exit_long=false,
        signal_exit_short=false,
        stop_loss_ratio_long=sl_long or none,
        stop_loss_ratio_short=sl_short or none,
        take_profit_ratio_long=tp_long or none,
        take_profit_ratio_short=tp_short or none,
        stop_loss_distance_long=none,
        stop_loss_distance_short=none,
        take_profit_distance_long=none,
        take_profit_distance_short=none,
        stop_ready_long=stop_ready_long or false,
        stop_ready_short=stop_ready_short or false,
        signal_by_profile_long=signal_long or empty_profiles,
        signal_by_profile_short=signal_short or empty_profiles,
        stop_loss_by_profile={},
        take_profit_by_profile={},
        rule_evidence=rule_evidence,
    )


def _evaluation(
    entries: tuple[SideEntryEvaluation, ...], exit_policy: ExitPolicyEvaluation
) -> object:
    return SimpleNamespace(entries=entries, exit_policy=exit_policy)


def _build(evaluation: object, bar_count: int = 4):
    return build_historical_execution_projection(
        strategy_id="ema_pullback",
        config_hash="cfg",
        market=_MARKET,
        requested_range=_RANGE,
        market_data_hash="hash",
        bar_count=bar_count,
        evaluation=evaluation,  # type: ignore[arg-type]
    )


# --- executable entry opportunity selection -------------------------------


def test_no_opportunity_when_entry_allowed_but_not_protection_ready() -> None:
    evaluation = _evaluation(
        entries=(_entries("long", (True, True, True, True)),),
        exit_policy=_exit_policy(bar_count=4, stop_ready_long=(False, False, False, False)),
    )
    projection = _build(evaluation)
    assert projection.entry_opportunities == ()


def test_no_opportunity_when_protection_ready_but_entry_not_allowed() -> None:
    evaluation = _evaluation(
        entries=(_entries("long", (False, False, False, False)),),
        exit_policy=_exit_policy(bar_count=4, stop_ready_long=(True, True, True, True)),
    )
    projection = _build(evaluation)
    assert projection.entry_opportunities == ()


def test_opportunity_exists_only_where_both_hold() -> None:
    evaluation = _evaluation(
        entries=(_entries("long", (True, False, True, True)),),
        exit_policy=_exit_policy(bar_count=4, stop_ready_long=(True, True, False, True)),
    )
    projection = _build(evaluation)
    assert [o.bar_index for o in projection.entry_opportunities] == [0, 3]
    assert all(o.side == "long" for o in projection.entry_opportunities)


# --- locked_exit_profile capture -------------------------------------------


def test_locked_exit_profile_is_the_profile_active_at_that_bar() -> None:
    evaluation = _evaluation(
        entries=(_entries("long", (True, True, True, True)),),
        exit_policy=_exit_policy(
            bar_count=4,
            stop_ready_long=(True, True, True, True),
            profile_long=("aligned", "countertrend", "neutral", "aligned"),
        ),
    )
    projection = _build(evaluation)
    assert [o.locked_exit_profile for o in projection.entry_opportunities] == [
        "aligned",
        "countertrend",
        "neutral",
        "aligned",
    ]


# --- initial_stop/initial_take optionality ----------------------------------


def test_both_legs_null_when_no_rule_configured() -> None:
    evaluation = _evaluation(
        entries=(_entries("long", (True,)),),
        exit_policy=_exit_policy(bar_count=1, stop_ready_long=(True,)),
    )
    projection = _build(evaluation, bar_count=1)
    (opportunity,) = projection.entry_opportunities
    assert opportunity.initial_stop is None
    assert opportunity.initial_take is None


def test_take_only_leg_leaves_stop_null() -> None:
    evidence = (
        ExitRuleEvidence(
            "tp1", "atr_take_profit", "take_profit", "always_on", None, distance_ratio=(0.02,)
        ),
    )
    evaluation = _evaluation(
        entries=(_entries("long", (True,)),),
        exit_policy=_exit_policy(
            bar_count=1,
            stop_ready_long=(True,),
            tp_long=(0.02,),
            rule_evidence=evidence,
        ),
    )
    projection = _build(evaluation, bar_count=1)
    (opportunity,) = projection.entry_opportunities
    assert opportunity.initial_stop is None
    assert opportunity.initial_take is not None
    assert opportunity.initial_take.ratio == 0.02
    assert opportunity.initial_take.attribution.rule_id == "tp1"
    assert opportunity.initial_take.attribution.exit_kind == "take_profit"


# --- multi-rule attribution: min() + first-in-declared-order tie-break -----


def test_attribution_picks_the_rule_matching_the_aggregate_min() -> None:
    # two stop rules, distances 0.02 and 0.01 -- aggregate (min) is 0.01,
    # attribution owner must be the 0.01 rule (sl_tight), not the first
    # rule in declared order (sl_wide is declared first but loses on value).
    evidence = (
        ExitRuleEvidence(
            "sl_wide", "atr_stop_loss", "stop_loss", "always_on", None, distance_ratio=(0.02,)
        ),
        ExitRuleEvidence(
            "sl_tight", "atr_stop_loss", "stop_loss", "always_on", None, distance_ratio=(0.01,)
        ),
    )
    evaluation = _evaluation(
        entries=(_entries("long", (True,)),),
        exit_policy=_exit_policy(
            bar_count=1, stop_ready_long=(True,), sl_long=(0.01,), rule_evidence=evidence
        ),
    )
    projection = _build(evaluation, bar_count=1)
    (opportunity,) = projection.entry_opportunities
    assert opportunity.initial_stop is not None
    assert opportunity.initial_stop.ratio == 0.01
    assert opportunity.initial_stop.attribution.rule_id == "sl_tight"


def test_exact_tie_picks_first_in_declared_order() -> None:
    # two stop rules with numerically identical distances -- declared
    # order (as they appear in rule_evidence, which mirrors config
    # declaration order) breaks the tie: first one wins.
    evidence = (
        ExitRuleEvidence(
            "sl_a", "atr_stop_loss", "stop_loss", "always_on", None, distance_ratio=(0.015,)
        ),
        ExitRuleEvidence(
            "sl_b", "atr_stop_loss", "stop_loss", "always_on", None, distance_ratio=(0.015,)
        ),
    )
    evaluation = _evaluation(
        entries=(_entries("long", (True,)),),
        exit_policy=_exit_policy(
            bar_count=1, stop_ready_long=(True,), sl_long=(0.015,), rule_evidence=evidence
        ),
    )
    projection = _build(evaluation, bar_count=1)
    (opportunity,) = projection.entry_opportunities
    assert opportunity.initial_stop is not None
    assert opportunity.initial_stop.attribution.rule_id == "sl_a"


def test_attribution_respects_group_scope_always_on_then_locked_profile() -> None:
    # a rule declared under a DIFFERENT (non-locked) profile must never
    # be selected, even if its distance would numerically match.
    evidence = (
        ExitRuleEvidence(
            "sl_countertrend",
            "atr_stop_loss",
            "stop_loss",
            "countertrend",
            None,
            distance_ratio=(0.01,),
        ),
        ExitRuleEvidence(
            "sl_aligned", "atr_stop_loss", "stop_loss", "aligned", None, distance_ratio=(0.01,)
        ),
    )
    evaluation = _evaluation(
        entries=(_entries("long", (True,)),),
        exit_policy=_exit_policy(
            bar_count=1,
            stop_ready_long=(True,),
            sl_long=(0.01,),
            profile_long=("aligned",),
            rule_evidence=evidence,
        ),
    )
    projection = _build(evaluation, bar_count=1)
    (opportunity,) = projection.entry_opportunities
    assert opportunity.locked_exit_profile == "aligned"
    assert opportunity.initial_stop is not None
    assert opportunity.initial_stop.attribution.rule_id == "sl_aligned"


# --- per-profile signal-exit indexing ---------------------------------------


def test_signal_exit_events_indexed_per_profile_not_flattened() -> None:
    evidence = (
        ExitRuleEvidence(
            "sig_neutral",
            "rsi_signal_exit",
            "signal",
            "neutral",
            "long",
            signal=(False, True, False),
        ),
        ExitRuleEvidence(
            "sig_aligned",
            "rsi_signal_exit",
            "signal",
            "aligned",
            "long",
            signal=(True, False, False),
        ),
    )
    evaluation = _evaluation(
        entries=(_entries("long", (False, False, False)),),
        exit_policy=_exit_policy(
            bar_count=3,
            signal_long={
                "aligned": (True, False, False),
                "countertrend": (False, False, False),
                "neutral": (False, True, False),
            },
            rule_evidence=evidence,
        ),
    )
    projection = _build(evaluation, bar_count=3)
    aligned_events = projection.signal_exit_events.long["aligned"]
    neutral_events = projection.signal_exit_events.long["neutral"]
    countertrend_events = projection.signal_exit_events.long["countertrend"]

    assert [e.bar_index for e in aligned_events] == [0]
    assert aligned_events[0].candidates[0].attribution.rule_id == "sig_aligned"
    assert [e.bar_index for e in neutral_events] == [1]
    assert neutral_events[0].candidates[0].attribution.rule_id == "sig_neutral"
    assert countertrend_events == ()


def test_bar_with_no_opportunity_and_no_signal_carries_no_data() -> None:
    evaluation = _evaluation(
        entries=(_entries("long", (False, False)),),
        exit_policy=_exit_policy(bar_count=2),
    )
    projection = _build(evaluation, bar_count=2)
    assert projection.entry_opportunities == ()
    assert all(events == () for events in projection.signal_exit_events.long.values())
    assert all(events == () for events in projection.signal_exit_events.short.values())


# --- corrective pass: fail-loud invariants + exact epsilon ------------------


def test_simultaneous_long_and_short_opportunity_fails_loud() -> None:
    exit_policy = _exit_policy(
        bar_count=1,
        stop_ready_long=(True,),
        stop_ready_short=(True,),
    )
    evaluation = _evaluation(
        entries=(
            _entries("long", (True,)),
            _entries("short", (True,)),
        ),
        exit_policy=exit_policy,
    )
    with pytest.raises(AssertionError, match="simultaneous executable long and short"):
        _build(evaluation, bar_count=1)


def test_non_simultaneous_long_and_short_does_not_fail() -> None:
    evaluation = _evaluation(
        entries=(
            _entries("long", (True, False)),
            _entries("short", (False, True)),
        ),
        exit_policy=_exit_policy(
            bar_count=2,
            stop_ready_long=(True, False),
            stop_ready_short=(False, True),
        ),
    )
    projection = _build(evaluation, bar_count=2)
    assert [(o.bar_index, o.side) for o in projection.entry_opportunities] == [
        (0, "long"),
        (1, "short"),
    ]


def test_signal_fired_with_no_matching_rule_candidate_fails_loud() -> None:
    # signal_by_profile says a signal fired for "aligned", but rule_evidence
    # has no signal rule scoped to that group -- internal inconsistency.
    evaluation = _evaluation(
        entries=(_entries("long", (False,)),),
        exit_policy=_exit_policy(
            bar_count=1,
            signal_long={"aligned": (True,), "countertrend": (False,), "neutral": (False,)},
            rule_evidence=(),
        ),
    )
    with pytest.raises(AssertionError, match="no matching rule_evidence candidate"):
        _build(evaluation, bar_count=1)


def test_epsilon_matches_old_bbb_formula_exactly() -> None:
    # eps = 1e-9 * max(1.0, abs(aggregate_ratio)); a candidate just inside
    # tolerance (relative to the AGGREGATE value, not the candidate) must
    # match, and just outside must not.
    aggregate = 100.0
    eps = 1e-9 * max(1.0, abs(aggregate))
    just_inside = aggregate + eps * 0.5
    just_outside = aggregate + eps * 2.0

    evidence_inside = (
        ExitRuleEvidence(
            "sl_inside",
            "atr_stop_loss",
            "stop_loss",
            "always_on",
            None,
            distance_ratio=(just_inside,),
        ),
    )
    evaluation_inside = _evaluation(
        entries=(_entries("long", (True,)),),
        exit_policy=_exit_policy(
            bar_count=1,
            stop_ready_long=(True,),
            sl_long=(aggregate,),
            rule_evidence=evidence_inside,
        ),
    )
    projection = _build(evaluation_inside, bar_count=1)
    (opportunity,) = projection.entry_opportunities
    assert opportunity.initial_stop is not None
    assert opportunity.initial_stop.attribution.rule_id == "sl_inside"

    evidence_outside = (
        ExitRuleEvidence(
            "sl_outside",
            "atr_stop_loss",
            "stop_loss",
            "always_on",
            None,
            distance_ratio=(just_outside,),
        ),
    )
    evaluation_outside = _evaluation(
        entries=(_entries("long", (True,)),),
        exit_policy=_exit_policy(
            bar_count=1,
            stop_ready_long=(True,),
            sl_long=(aggregate,),
            rule_evidence=evidence_outside,
        ),
    )
    with pytest.raises(AssertionError, match="no matching rule_evidence entry"):
        _build(evaluation_outside, bar_count=1)
