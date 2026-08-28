"""I2 -- Engine: Historical Semantics Proof (Master Plan,
`compact-strategy-evaluation-boundary-v1`).

Proves the I1 pure builder (`build_historical_execution_projection`)
reproduces old-BBB historical execution-policy semantics on a
profile-sensitive adversarial spec where `aligned`/`countertrend`/
`neutral` carry genuinely distinct stop-loss, take-profit, and
signal-exit rules, and where a locked entry profile must remain
independently retrievable after the market's *current* profile has
drifted away from it.

Design
------
`evaluate_exit_policy()` (`strategy_engine/strategies/ema_pullback/
exits.py`) is called directly -- unmodified, real production code,
already covered by its own unit suite (`test_ema_pullback_exits.py`).
It is the *reference oracle's raw material*: `rule_evidence` (per-rule
signal/distance series, built in real declared config order --
always_on first, then aligned/countertrend/neutral, each in their own
declared list order -- exactly the order the I0 spec's attribution
algorithm requires) and the per-profile aggregate ratios
(`stop_loss_by_profile`/`take_profit_by_profile`) it already computes
via `_min()`/`_select()`.

This test's own `_reference_leg_attribution`/`_reference_signal_
candidates` functions independently re-derive the old-BBB selection/
attribution algorithm (group filter: `always_on` + locked profile only;
first match in declared order; epsilon `1e-9 * max(1.0,
abs(aggregate_ratio))`) directly from that raw `rule_evidence` -- they
do NOT call anything in `historical_execution_projection.py`. Only the
*production I1 builder itself* (`build_historical_execution_projection`)
is exercised as the thing under test; the reference functions here are
a from-scratch restatement of the I0 spec's normative algorithm, not a
copy of the builder's own helpers -- this is what keeps the comparison
from validating the builder against itself.

`context_consumption.py::build_context_consumption_evidence` (the layer
that resolves raw HTF context state into `aligned`/`countertrend`/
`neutral` per side) is deliberately bypassed: a synthetic
`ContextConsumptionRecord` supplies `profile_long`/`profile_short`
ground truth directly. That resolution layer is untouched, pre-existing
code outside I1's scope -- I2 is about whether the *new builder*
correctly reads and preserves whatever profile was active, not about
re-proving how the profile itself gets resolved from indicator state.

Scenario
--------
33 bars, three 11-bar segments. `profile_long`/`profile_short` ground
truth is set directly (not derived from a raw indicator context) so
every segment boundary is an exact, known profile transition:

  segment A (bars  0-10): long=aligned,      short=countertrend
  segment B (bars 11-21): long=countertrend, short=aligned
  segment C (bars 22-32): long=neutral,      short=neutral

Exit-policy rules (real component ids from `exits.py`'s
`_DISTANCE_COMPONENTS`/`_SIGNAL_COMPONENTS` registries):

  always_on:    sl_always  (constant_usd_stop_loss,  usd_distance=100)
                sig_always_ema (ema_close_loss_exit, ema period=2)
  aligned:      sl_aligned (constant_usd_stop_loss,  usd_distance=10)
                tp_aligned (constant_usd_take_profit, usd_distance=20)
                sig_aligned_ema (ema_close_loss_exit, ema period=2)
  countertrend: sl_countertrend (constant_usd_stop_loss, usd_distance=100)
                tp_countertrend (constant_usd_take_profit, usd_distance=40)
                sig_countertrend_ema (ema_close_loss_exit, ema period=3)
  neutral:      sig_neutral_ema (ema_close_loss_exit, ema period=5)
                (no SL/TP rule of its own -- relies on always_on's SL
                only; no TP configured at all)

`close` is held constant at 1.0 across every bar, so a
`constant_usd_*` rule's ratio equals its configured `usd_distance`
exactly -- this makes the aggregation/tie-break arithmetic exact
rather than approximate:

  - aligned's own SL (10) beats always_on's SL (100) -- profile rule
    wins on value.
  - countertrend's own SL (100) exactly TIES always_on's SL (100) --
    declared order (always_on first) must win the tie.
  - neutral has no SL of its own -- always_on's SL (100) is the only
    candidate, proving the always_on-only fallback case.
  - neutral has no TP rule anywhere -- `initial_take` must be `None`,
    proving independent per-leg nullability.

Entry opportunities are placed (via directly-constructed
`SideEntryEvaluation`, matching this repo's existing white-box test
convention for this builder) at bars that are never simultaneously
`True` for both sides, so all three profiles are exercised for BOTH
long and short without tripping I1's simultaneous-long-short fail-loud
invariant:

  long:  bar 0 (aligned), bar 11 (countertrend), bar 22 (neutral)
  short: bar 5 (countertrend), bar 16 (aligned), bar 27 (neutral)
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import NativeFeatureFrame
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.contracts import ExecutableEntryOpportunity, LiveStrategySpec
from strategy_engine.strategies.ema_pullback.context_consumption import ContextConsumptionRecord
from strategy_engine.strategies.ema_pullback.exits import ExitRuleEvidence, evaluate_exit_policy
from strategy_engine.strategies.ema_pullback.risk import RiskMask, SideEntryEvaluation
from strategy_engine.strategies.historical_execution_projection import (
    build_historical_execution_projection,
)

_BAR_COUNT = 33
_SEGMENT = 11
_MARKET = MarketStream(ticker="BTCUSDT.P", base_timeframe="5m")
_RANGE = TimeRange(from_ms=0, to_ms=300_000 * _BAR_COUNT)

_LONG_ENTRY_BARS = {0, 11, 22}
_SHORT_ENTRY_BARS = {5, 16, 27}

_EPS_REL = 1e-9


def _raw_spec() -> dict[str, object]:
    return {
        "trade_sides": ["long", "short"],
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "components": {"blockers": []},
        "setups": [],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "sl_always",
                            "component_id": "constant_usd_stop_loss",
                            "exit_kind": "stop_loss",
                            "usd_distance": 100.0,
                        },
                        {
                            "instance_id": "sig_always_ema",
                            "component_id": "ema_close_loss_exit",
                            "exit_kind": "signal",
                            "ema": {"period": 2},
                            "confirm_bars": 1,
                        },
                    ]
                },
                "profiles": {
                    "aligned": {
                        "exits": [
                            {
                                "instance_id": "sl_aligned",
                                "component_id": "constant_usd_stop_loss",
                                "exit_kind": "stop_loss",
                                "usd_distance": 10.0,
                            },
                            {
                                "instance_id": "tp_aligned",
                                "component_id": "constant_usd_take_profit",
                                "exit_kind": "take_profit",
                                "usd_distance": 20.0,
                            },
                            {
                                "instance_id": "sig_aligned_ema",
                                "component_id": "ema_close_loss_exit",
                                "exit_kind": "signal",
                                "ema": {"period": 2},
                                "confirm_bars": 1,
                            },
                        ]
                    },
                    "countertrend": {
                        "exits": [
                            {
                                "instance_id": "sl_countertrend",
                                "component_id": "constant_usd_stop_loss",
                                "exit_kind": "stop_loss",
                                "usd_distance": 100.0,
                            },
                            {
                                "instance_id": "tp_countertrend",
                                "component_id": "constant_usd_take_profit",
                                "exit_kind": "take_profit",
                                "usd_distance": 40.0,
                            },
                            {
                                "instance_id": "sig_countertrend_ema",
                                "component_id": "ema_close_loss_exit",
                                "exit_kind": "signal",
                                "ema": {"period": 3},
                                "confirm_bars": 1,
                            },
                        ]
                    },
                    "neutral": {
                        "exits": [
                            {
                                "instance_id": "sig_neutral_ema",
                                "component_id": "ema_close_loss_exit",
                                "exit_kind": "signal",
                                "ema": {"period": 5},
                                "confirm_bars": 1,
                            },
                        ]
                    },
                },
            },
            "exit_management": {},
        },
    }


def _profile_long() -> tuple[str, ...]:
    return (
        tuple("aligned" for _ in range(_SEGMENT))
        + tuple("countertrend" for _ in range(_SEGMENT))
        + tuple("neutral" for _ in range(_SEGMENT))
    )


def _profile_short() -> tuple[str, ...]:
    return (
        tuple("countertrend" for _ in range(_SEGMENT))
        + tuple("aligned" for _ in range(_SEGMENT))
        + tuple("neutral" for _ in range(_SEGMENT))
    )


def _ema_series(modulus: int, high_remainders: tuple[int, ...]) -> tuple[float, ...]:
    # 2.0 => close(1.0) < ema (long signal condition true, short false)
    # 0.5 => close(1.0) > ema (short signal condition true, long false)
    return tuple(2.0 if (i % modulus) in high_remainders else 0.5 for i in range(_BAR_COUNT))


def _frame(plan: object) -> NativeFeatureFrame:
    ema_p2_col = plan.ema_columns[("base", 2)]  # type: ignore[attr-defined]
    ema_p3_col = plan.ema_columns[("base", 3)]  # type: ignore[attr-defined]
    ema_p5_col = plan.ema_columns[("base", 5)]  # type: ignore[attr-defined]

    market_bars = tuple(
        MarketBar(
            i * 300_000,
            Decimal("1"),
            Decimal("1.1"),
            Decimal("0.9"),
            Decimal("1"),
            Decimal("10"),
        )
        for i in range(_BAR_COUNT)
    )
    return NativeFeatureFrame(
        market=_MARKET,
        requested_range=_RANGE,
        time_ms=tuple(bar.open_time_ms for bar in market_bars),
        series={
            ema_p2_col: _ema_series(4, (0, 1)),
            ema_p3_col: _ema_series(5, (0, 1)),
            ema_p5_col: _ema_series(6, (0, 1, 2)),
        },
        validity={},
        plan_hash="i2-plan-hash",
        market_data_hash="i2-market-hash",
        market_bars=market_bars,
    )


def _entries() -> tuple[SideEntryEvaluation, ...]:
    long_allowed = tuple(i in _LONG_ENTRY_BARS for i in range(_BAR_COUNT))
    short_allowed = tuple(i in _SHORT_ENTRY_BARS for i in range(_BAR_COUNT))
    return (
        SideEntryEvaluation(
            side="long",
            risk=RiskMask(component_id="no_risk_filter", side="long", allowed=long_allowed),
            entry_allowed=long_allowed,
        ),
        SideEntryEvaluation(
            side="short",
            risk=RiskMask(component_id="no_risk_filter", side="short", allowed=short_allowed),
            entry_allowed=short_allowed,
        ),
    )


def _build_projection() -> tuple[object, tuple[ExitRuleEvidence, ...]]:
    strategy = LiveStrategySpec(strategy_id="ema_pullback", raw_spec=_raw_spec())
    plan = BuildStrategyFeaturePlan().execute(strategy)
    frame = _frame(plan)
    profile_long = _profile_long()
    profile_short = _profile_short()
    raw_state = (
        tuple("up" for _ in range(_SEGMENT))
        + tuple("down" for _ in range(_SEGMENT))
        + tuple("neutral" for _ in range(_SEGMENT))
    )
    consumption = (
        ContextConsumptionRecord(
            role="exit_policy",
            context_ref="htf",
            policy_id="exit_profile_by_htf_state",
            side=None,
            component_id="exit_policy",
            instance_id=None,
            raw_state=raw_state,
            profile_long=profile_long,
            profile_short=profile_short,
        ),
    )
    exit_policy = evaluate_exit_policy(strategy.raw_spec, frame, plan, consumption)
    evaluation = SimpleNamespace(entries=_entries(), exit_policy=exit_policy)
    projection = build_historical_execution_projection(
        strategy_id="ema_pullback",
        config_hash="i2-config-hash",
        market=_MARKET,
        requested_range=_RANGE,
        market_data_hash="i2-market-hash",
        bar_count=_BAR_COUNT,
        evaluation=evaluation,  # type: ignore[arg-type]
    )
    return projection, exit_policy.rule_evidence


# --- independent reference oracle (I0-spec algorithm, not builder code) ----


def _close_enough_reference(candidate: float, aggregate_ratio: float) -> bool:
    eps = _EPS_REL * max(1.0, abs(aggregate_ratio))
    return abs(candidate - aggregate_ratio) <= eps


def _reference_leg_attribution(
    rule_evidence: tuple[ExitRuleEvidence, ...],
    *,
    exit_kind: str,
    locked_profile: str,
    bar_index: int,
    aggregate_ratio: float,
) -> tuple[str, str] | None:
    for rule in rule_evidence:
        if rule.exit_kind != exit_kind:
            continue
        if rule.group not in ("always_on", locked_profile):
            continue
        if rule.distance_ratio is None:
            continue
        value = rule.distance_ratio[bar_index]
        if value is None:
            continue
        if _close_enough_reference(value, aggregate_ratio):
            return (rule.instance_id, rule.component_id)
    return None


def _reference_signal_candidates(
    rule_evidence: tuple[ExitRuleEvidence, ...],
    *,
    side: str,
    profile: str,
    bar_index: int,
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for rule in rule_evidence:
        if rule.exit_kind != "signal":
            continue
        if rule.side != side:
            continue
        if rule.group not in ("always_on", profile):
            continue
        if rule.signal is None:
            continue
        if rule.signal[bar_index]:
            result.append((rule.instance_id, rule.component_id))
    return result


# --- A. executable entry opportunities + absence of standalone stop_ready --


def test_no_standalone_stop_ready_field_on_the_contract() -> None:
    assert "stop_ready" not in ExecutableEntryOpportunity.__dataclass_fields__


def test_executable_entry_opportunities_match_exactly_the_configured_bars() -> None:
    projection, _ = _build_projection()
    long_bars = {o.bar_index for o in projection.entry_opportunities if o.side == "long"}
    short_bars = {o.bar_index for o in projection.entry_opportunities if o.side == "short"}
    assert long_bars == _LONG_ENTRY_BARS
    assert short_bars == _SHORT_ENTRY_BARS


# --- B. locked_exit_profile equals the profile active at that exact bar ----


def test_locked_exit_profile_matches_ground_truth_for_every_opportunity() -> None:
    projection, _ = _build_projection()
    profile_long = _profile_long()
    profile_short = _profile_short()
    for opportunity in projection.entry_opportunities:
        expected = (
            profile_long[opportunity.bar_index]
            if opportunity.side == "long"
            else profile_short[opportunity.bar_index]
        )
        assert opportunity.locked_exit_profile == expected

    # all three profile values are covered, for BOTH sides
    long_profiles = {
        o.locked_exit_profile for o in projection.entry_opportunities if o.side == "long"
    }
    short_profiles = {
        o.locked_exit_profile for o in projection.entry_opportunities if o.side == "short"
    }
    assert long_profiles == {"aligned", "countertrend", "neutral"}
    assert short_profiles == {"aligned", "countertrend", "neutral"}


# --- C/D. initial stop/take: aggregation, declared-order tie-break, --------
# --- always_on fallback, independent nullability ---------------------------


def _opportunity(projection: object, *, side: str, bar_index: int) -> ExecutableEntryOpportunity:
    for o in projection.entry_opportunities:  # type: ignore[attr-defined]
        if o.side == side and o.bar_index == bar_index:
            return o
    raise AssertionError(f"no opportunity for side={side!r} bar_index={bar_index}")


def test_profile_rule_wins_over_always_on_when_its_value_is_smaller() -> None:
    # long/aligned (bar 0): sl_aligned=10 beats always_on's sl_always=100
    projection, _ = _build_projection()
    opportunity = _opportunity(projection, side="long", bar_index=0)
    assert opportunity.initial_stop is not None
    assert opportunity.initial_stop.ratio == 10.0
    assert opportunity.initial_stop.attribution.rule_id == "sl_aligned"
    assert opportunity.initial_stop.attribution.component_id == "constant_usd_stop_loss"
    assert opportunity.initial_stop.attribution.exit_kind == "stop_loss"
    assert opportunity.initial_take is not None
    assert opportunity.initial_take.ratio == 20.0
    assert opportunity.initial_take.attribution.rule_id == "tp_aligned"
    assert opportunity.initial_take.attribution.exit_kind == "take_profit"


def test_exact_tie_between_always_on_and_profile_rule_favors_declared_order() -> None:
    # long/countertrend (bar 11): sl_countertrend=100 exactly ties
    # always_on's sl_always=100 -- declared order (always_on first) wins.
    projection, _ = _build_projection()
    opportunity = _opportunity(projection, side="long", bar_index=11)
    assert opportunity.initial_stop is not None
    assert opportunity.initial_stop.ratio == 100.0
    assert opportunity.initial_stop.attribution.rule_id == "sl_always"
    assert opportunity.initial_take is not None
    assert opportunity.initial_take.ratio == 40.0
    assert opportunity.initial_take.attribution.rule_id == "tp_countertrend"


def test_neutral_profile_falls_back_to_always_on_only_and_has_no_take_leg() -> None:
    # long/neutral (bar 22): no SL/TP rule of its own -- only always_on's
    # SL is a candidate; no TP rule anywhere for neutral.
    projection, _ = _build_projection()
    opportunity = _opportunity(projection, side="long", bar_index=22)
    assert opportunity.initial_stop is not None
    assert opportunity.initial_stop.ratio == 100.0
    assert opportunity.initial_stop.attribution.rule_id == "sl_always"
    assert opportunity.initial_take is None


def test_short_side_reproduces_the_same_profile_semantics() -> None:
    projection, _ = _build_projection()
    # short/countertrend (bar 5): same tie-break as long/countertrend.
    countertrend_opportunity = _opportunity(projection, side="short", bar_index=5)
    assert countertrend_opportunity.initial_stop is not None
    assert countertrend_opportunity.initial_stop.attribution.rule_id == "sl_always"
    assert countertrend_opportunity.initial_take is not None
    assert countertrend_opportunity.initial_take.attribution.rule_id == "tp_countertrend"

    # short/aligned (bar 16): same profile-rule-wins as long/aligned.
    aligned_opportunity = _opportunity(projection, side="short", bar_index=16)
    assert aligned_opportunity.initial_stop is not None
    assert aligned_opportunity.initial_stop.attribution.rule_id == "sl_aligned"
    assert aligned_opportunity.initial_take is not None
    assert aligned_opportunity.initial_take.attribution.rule_id == "tp_aligned"

    # short/neutral (bar 27): always_on-only fallback, no take leg.
    neutral_opportunity = _opportunity(projection, side="short", bar_index=27)
    assert neutral_opportunity.initial_stop is not None
    assert neutral_opportunity.initial_stop.attribution.rule_id == "sl_always"
    assert neutral_opportunity.initial_take is None


def test_every_opportunity_leg_matches_the_independent_reference_oracle() -> None:
    projection, rule_evidence = _build_projection()
    for opportunity in projection.entry_opportunities:
        for leg, exit_kind in (
            (opportunity.initial_stop, "stop_loss"),
            (opportunity.initial_take, "take_profit"),
        ):
            if leg is None:
                continue
            reference = _reference_leg_attribution(
                rule_evidence,
                exit_kind=exit_kind,
                locked_profile=opportunity.locked_exit_profile,
                bar_index=opportunity.bar_index,
                aggregate_ratio=leg.ratio,
            )
            assert reference is not None
            assert (leg.attribution.rule_id, leg.attribution.component_id) == reference


# --- E. signal-exit streams by (side, profile): sparse, independent, ------
# --- ordered exactly as the reference oracle reproduces --------------------


def test_signal_streams_match_reference_oracle_for_every_side_profile_bar() -> None:
    projection, rule_evidence = _build_projection()
    for side, streams in (
        ("long", projection.signal_exit_events.long),
        ("short", projection.signal_exit_events.short),
    ):
        for profile, events in streams.items():
            reference_bars = {
                i
                for i in range(_BAR_COUNT)
                if _reference_signal_candidates(
                    rule_evidence, side=side, profile=profile, bar_index=i
                )
            }
            assert {e.bar_index for e in events} == reference_bars
            for event in events:
                expected = _reference_signal_candidates(
                    rule_evidence, side=side, profile=profile, bar_index=event.bar_index
                )
                actual = [
                    (c.attribution.rule_id, c.attribution.component_id) for c in event.candidates
                ]
                assert actual == expected
                assert all(c.attribution.exit_kind == "signal" for c in event.candidates)


# --- F. multiple simultaneous signal rules, canonical declared order -------


def test_multiple_simultaneous_signal_rules_preserve_declared_order() -> None:
    # long/aligned at bar 0: sig_always_ema (always_on, declared first) and
    # sig_aligned_ema (aligned's own) both reference ema period 2 -- both
    # fire together whenever close < ema_p2, which bar 0 satisfies
    # (0 % 4 in (0, 1) -> ema_p2[0] = 2.0).
    projection, rule_evidence = _build_projection()
    events = {e.bar_index: e for e in projection.signal_exit_events.long["aligned"]}
    assert 0 in events
    candidate_ids = [c.attribution.rule_id for c in events[0].candidates]
    assert candidate_ids == ["sig_always_ema", "sig_aligned_ema"]
    reference = _reference_signal_candidates(
        rule_evidence, side="long", profile="aligned", bar_index=0
    )
    assert [rule_id for rule_id, _ in reference] == candidate_ids


# --- G. locked-profile-survives-drift proof: I4's future lookup pattern ----


def test_locked_profile_stream_is_correct_after_current_profile_drifts_away() -> None:
    """Entry opportunity at bar 0 locks `aligned` for the long side.
    Segment B (bars 11-21) is where the market's *current* long profile
    has drifted to `countertrend` -- yet a caller that saved
    `locked_exit_profile == "aligned"` at fill must still retrieve
    correct `aligned`-stream facts for those later bars, independent of
    what the current bar's active profile is. This is exactly the fact
    shape I4 (Research) will consume; no trade state is held here."""

    projection, rule_evidence = _build_projection()
    entry_opportunity = _opportunity(projection, side="long", bar_index=0)
    assert entry_opportunity.locked_exit_profile == "aligned"
    saved_profile = entry_opportunity.locked_exit_profile

    profile_long = _profile_long()
    later_bars_with_current_profile_drifted = [
        i for i in range(11, 22) if profile_long[i] != saved_profile
    ]
    assert later_bars_with_current_profile_drifted == list(range(11, 22))  # sanity: all drifted

    saved_stream = {e.bar_index: e for e in projection.signal_exit_events.long[saved_profile]}
    checked_at_least_one_event = False
    for bar_index in later_bars_with_current_profile_drifted:
        reference = _reference_signal_candidates(
            rule_evidence, side="long", profile=saved_profile, bar_index=bar_index
        )
        if bar_index in saved_stream:
            checked_at_least_one_event = True
            actual = [
                (c.attribution.rule_id, c.attribution.component_id)
                for c in saved_stream[bar_index].candidates
            ]
            assert actual == reference
        else:
            assert reference == []
    assert checked_at_least_one_event


# --- H. fail-closed regression fence: no I1 invariant was silently --------
# --- weakened to make this larger real-data scenario pass ------------------


def test_full_scenario_builds_without_tripping_any_fail_loud_invariant() -> None:
    # If this function returns at all, none of build_historical_execution_
    # projection's AssertionError fail-loud paths fired for this scenario
    # -- no silent widening of I1's invariants was needed.
    projection, _ = _build_projection()
    assert len(projection.entry_opportunities) == len(_LONG_ENTRY_BARS) + len(_SHORT_ENTRY_BARS)
