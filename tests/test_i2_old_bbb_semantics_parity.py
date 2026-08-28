"""I2 corrective pass -- Level 2 proof against actual old-BBB semantics
(`compact-strategy-evaluation-boundary-v1`, Master Plan).

`test_i2_historical_semantics_proof.py` (kept, unmodified, still green)
proves internal consistency: `current strategy_engine.evaluate_exit_
policy()` output -> I1 builder, checked against reference helpers this
migration's own author wrote by re-reading the I0 spec. That is Level 1
-- useful (it proves the I1 builder's *structural* correctness against
its own declared algorithm), but insufficient for the I2 gate on its
own: if `evaluate_exit_policy()` itself already diverged from old BBB,
both sides of that comparison could be consistently wrong together.

This file is Level 2: it computes expected attribution using the
ACTUAL old-BBB algorithm -- `_agg_sl_tp_at_entry`/`_pick_distance_
instance` and the signal-winner loop from `classify_exit_attribution`,
copied character-for-character from `roman-vyl/_bbb_new_gen` commit
`cddc83663911f646c9bcf2ecfb37b3bed6f4b1d4`
(`research/strategies/ema_pullback/execution/exit_attribution.py`) into
`_old_bbb_exit_attribution_reference.py` -- see that file's docstring
for exact provenance and the byte-diff verification of the copy. This
test imports those functions directly; it does not restate them.

The SAME adversarial scenario from `test_i2_historical_semantics_
proof.py` is reused (imported, not duplicated) -- same rule
configuration, same profile-drift sequence, same entry bars. What
changes is the *expected side*: instead of a test-local reference
helper, expected attribution/selection now comes from executing old
BBB's own functions against the real per-rule series
(`evaluate_exit_policy()`'s `rule_evidence`/`stop_loss_by_profile`/
`take_profit_by_profile` -- current Engine's real, already-tested
production output, used here only as *input data*, not as the source
of the selection algorithm being verified).
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
from _old_bbb_exit_attribution_reference import (
    ExitAttributionContext,
    _agg_sl_tp_at_entry,
    _first_fired_signal_instance,
    _pick_distance_instance,
)
from test_i2_historical_semantics_proof import (
    _BAR_COUNT,
    _LONG_ENTRY_BARS,
    _SHORT_ENTRY_BARS,
    _entries,
    _frame,
    _opportunity,
    _profile_long,
    _profile_short,
    _raw_spec,
)

from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.contracts import LiveStrategySpec
from strategy_engine.strategies.ema_pullback.context_consumption import ContextConsumptionRecord
from strategy_engine.strategies.ema_pullback.exits import ExitRuleEvidence, evaluate_exit_policy
from strategy_engine.strategies.historical_execution_projection import (
    build_historical_execution_projection,
)

_MARKET = MarketStream(ticker="BTCUSDT.P", base_timeframe="5m")
_RANGE = TimeRange(from_ms=0, to_ms=300_000 * _BAR_COUNT)
_SEGMENT = 11


def _build_projection_and_context() -> tuple[object, ExitAttributionContext]:
    """Same scenario construction as `test_i2_historical_semantics_
    proof.py::_build_projection`, but also returns the full
    `ExitPolicyEvaluation` reshaped into old BBB's own
    `ExitAttributionContext` shape -- the only extra step needed to run
    old BBB's real functions against it."""

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

    rule_evidence: tuple[ExitRuleEvidence, ...] = exit_policy.rule_evidence
    index = pd.RangeIndex(_BAR_COUNT)
    ctx = ExitAttributionContext(
        index=index,
        instance_ids=tuple(r.instance_id for r in rule_evidence),
        exit_kinds=tuple(r.exit_kind for r in rule_evidence),
        long_signal_by_rule=tuple(
            pd.Series(r.signal, index=index)
            if r.exit_kind == "signal" and r.side == "long"
            else None
            for r in rule_evidence
        ),
        short_signal_by_rule=tuple(
            pd.Series(r.signal, index=index)
            if r.exit_kind == "signal" and r.side == "short"
            else None
            for r in rule_evidence
        ),
        distance_ratio_by_rule=tuple(
            pd.Series(r.distance_ratio, index=index)
            if r.exit_kind in ("stop_loss", "take_profit")
            else None
            for r in rule_evidence
        ),
        rule_groups=tuple(r.group for r in rule_evidence),
        sl_stop_agg_by_profile={
            profile: pd.Series(series, index=index)
            for profile, series in exit_policy.stop_loss_by_profile.items()
        },
        tp_stop_agg_by_profile={
            profile: pd.Series(series, index=index)
            for profile, series in exit_policy.take_profit_by_profile.items()
        },
    )
    return projection, ctx


# --- entry bars/sides/entry-time profiles: unchanged from Level 1, this ----
# --- file only strengthens the attribution/selection legs ------------------


def test_entry_bars_sides_and_profiles_still_match_the_configured_scenario() -> None:
    projection, _ = _build_projection_and_context()
    long_bars = {o.bar_index for o in projection.entry_opportunities if o.side == "long"}
    short_bars = {o.bar_index for o in projection.entry_opportunities if o.side == "short"}
    assert long_bars == _LONG_ENTRY_BARS
    assert short_bars == _SHORT_ENTRY_BARS


# --- initial stop/take + distance attribution, against verbatim old BBB ----


def test_stop_and_take_attribution_match_verbatim_old_bbb_for_every_opportunity() -> None:
    projection, ctx = _build_projection_and_context()
    checked_stop = 0
    checked_take = 0
    for opportunity in projection.entry_opportunities:
        sl_agg, tp_agg = _agg_sl_tp_at_entry(
            ctx, opportunity.bar_index, profile=opportunity.locked_exit_profile
        )

        if sl_agg is None:
            assert opportunity.initial_stop is None
        else:
            assert opportunity.initial_stop is not None
            assert opportunity.initial_stop.ratio == sl_agg
            expected_instance = _pick_distance_instance(
                ctx,
                opportunity.bar_index,
                exit_kind="stop_loss",
                agg_value=sl_agg,
                profile=opportunity.locked_exit_profile,
            )
            assert expected_instance is not None
            assert opportunity.initial_stop.attribution.rule_id == expected_instance
            checked_stop += 1

        if tp_agg is None:
            assert opportunity.initial_take is None
        else:
            assert opportunity.initial_take is not None
            assert opportunity.initial_take.ratio == tp_agg
            expected_instance = _pick_distance_instance(
                ctx,
                opportunity.bar_index,
                exit_kind="take_profit",
                agg_value=tp_agg,
                profile=opportunity.locked_exit_profile,
            )
            assert expected_instance is not None
            assert opportunity.initial_take.attribution.rule_id == expected_instance
            checked_take += 1

    # sanity: the scenario actually exercises both non-null and null legs
    assert checked_stop == len(projection.entry_opportunities)  # every opportunity has a stop
    assert 0 < checked_take < len(projection.entry_opportunities)  # neutral bars have none


def test_tie_break_matches_verbatim_old_bbb_pick_distance_instance() -> None:
    # long/countertrend (bar 11): sl_countertrend=100 exactly ties
    # always_on's sl_always=100. Old BBB's own _pick_distance_instance
    # (not this migration's restatement) must independently agree that
    # always_on wins.
    projection, ctx = _build_projection_and_context()
    opportunity = _opportunity(projection, side="long", bar_index=11)
    sl_agg, _ = _agg_sl_tp_at_entry(ctx, 11, profile="countertrend")
    assert sl_agg == 100.0
    expected = _pick_distance_instance(
        ctx, 11, exit_kind="stop_loss", agg_value=sl_agg, profile="countertrend"
    )
    assert expected == "sl_always"
    assert opportunity.initial_stop is not None
    assert opportunity.initial_stop.attribution.rule_id == expected


# --- signal events per side/profile + attribution/order --------------------


def test_signal_winner_matches_verbatim_old_bbb_for_every_side_profile_bar() -> None:
    projection, ctx = _build_projection_and_context()
    checked_fired = 0
    for side, streams in (
        ("long", projection.signal_exit_events.long),
        ("short", projection.signal_exit_events.short),
    ):
        for profile, events in streams.items():
            events_by_bar = {e.bar_index: e for e in events}
            for bar_index in range(_BAR_COUNT):
                old_bbb_winner = _first_fired_signal_instance(
                    ctx, direction=side, bar_index=bar_index, profile=profile
                )
                if old_bbb_winner is None:
                    assert bar_index not in events_by_bar
                    continue
                assert bar_index in events_by_bar
                first_candidate = events_by_bar[bar_index].candidates[0]
                assert first_candidate.attribution.rule_id == old_bbb_winner
                checked_fired += 1
    assert checked_fired > 0


def test_multi_candidate_first_slot_matches_verbatim_old_bbb_winner() -> None:
    # long/aligned at bar 0: sig_always_ema + sig_aligned_ema both fire.
    # Old BBB's own signal loop only ever reports ONE winner (the first
    # in declared order) for a realized exit -- the projection's
    # candidates[0] must be exactly that winner.
    projection, ctx = _build_projection_and_context()
    events = {e.bar_index: e for e in projection.signal_exit_events.long["aligned"]}
    assert 0 in events
    old_bbb_winner = _first_fired_signal_instance(
        ctx, direction="long", bar_index=0, profile="aligned"
    )
    assert old_bbb_winner == "sig_always_ema"
    assert events[0].candidates[0].attribution.rule_id == old_bbb_winner


# --- profile-drift locked-profile lookup, against verbatim old BBB ---------


def test_locked_profile_lookup_after_drift_matches_verbatim_old_bbb() -> None:
    projection, ctx = _build_projection_and_context()
    entry_opportunity = _opportunity(projection, side="long", bar_index=0)
    saved_profile = entry_opportunity.locked_exit_profile
    assert saved_profile == "aligned"

    saved_stream = {e.bar_index: e for e in projection.signal_exit_events.long[saved_profile]}
    checked = 0
    for bar_index in range(11, 22):  # segment B: current long profile is countertrend here
        old_bbb_winner = _first_fired_signal_instance(
            ctx, direction="long", bar_index=bar_index, profile=saved_profile
        )
        if old_bbb_winner is None:
            assert bar_index not in saved_stream
        else:
            assert bar_index in saved_stream
            assert saved_stream[bar_index].candidates[0].attribution.rule_id == old_bbb_winner
            checked += 1
    assert checked > 0
