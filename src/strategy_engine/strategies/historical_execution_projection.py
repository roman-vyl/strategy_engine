"""Pure builder: `EmaPullbackEvaluation -> HistoricalExecutionProjection`.

I1 of `compact-strategy-evaluation-boundary-v1` (Master Plan). Additive
only -- not wired to any route or application service yet (that's I7).
Built entirely from already-computed native outputs on
`EmaPullbackEvaluation`/`ExitPolicyEvaluation`; no string-boxing, no
recomputation of strategy semantics.

Multi-rule attribution algorithm (normative, `strategy-research-
execution-contract-v1` spec delta, verified against the reference
old-monolith model's `_compile_distance_series`/`_pick_distance_instance`
-- `exits.py:152-179`/`exit_attribution.py:155-178`):

1. `stop_loss_ratio_long[i]`/`take_profit_ratio_long[i]` (and `_short`)
   already ARE the reference model's `min()`-aggregated ratio for
   whichever profile is active at bar `i` (`exits.py`'s `_min`/
   `_select` pipeline) -- no aggregation is recomputed here.
2. `rule_evidence` is built in exactly the declared config order the
   algorithm requires: `always_on` rules first (in their declared
   list order), then each profile's own rules in `aligned`,
   `countertrend`, `neutral` order (in their declared list order) --
   `exits.py::_policy_rules` inserts dict keys in that order, and
   `evaluate_exit_policy` appends to `evidence` by iterating
   `groups.items()` in that same order. Filtering `rule_evidence` to
   `group in {"always_on", locked_profile}` and taking the first match
   (by numerical equality with the known aggregate ratio, within a
   small epsilon) reproduces the reference model's tie-break exactly:
   first-in-declared-order among values equal to the aggregate.
"""

from __future__ import annotations

from typing import Literal

from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.strategies.contracts import (
    ExecutableEntryOpportunity,
    ExitAttribution,
    HistoricalExecutionProjection,
    InitialProtectionLeg,
    SignalExitCandidate,
    SignalExitEvent,
    SignalExitProjection,
)
from strategy_engine.strategies.ema_pullback.evaluation import EmaPullbackEvaluation
from strategy_engine.strategies.ema_pullback.exits import ExitRuleEvidence

_EPS_REL = 1e-9


def _close_enough(a: float, b: float) -> bool:
    return abs(a - b) <= _EPS_REL * max(1.0, abs(a), abs(b))


def _pick_leg_attribution(
    rule_evidence: tuple[ExitRuleEvidence, ...],
    *,
    exit_kind: Literal["stop_loss", "take_profit"],
    locked_profile: str,
    bar_index: int,
    aggregate_ratio: float,
) -> ExitAttribution | None:
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
        if _close_enough(value, aggregate_ratio):
            return ExitAttribution(
                rule_id=rule.instance_id, component_id=rule.component_id, exit_kind=exit_kind
            )
    return None


def _leg(
    rule_evidence: tuple[ExitRuleEvidence, ...],
    *,
    exit_kind: Literal["stop_loss", "take_profit"],
    locked_profile: str,
    bar_index: int,
    ratio: float | None,
) -> InitialProtectionLeg | None:
    if ratio is None:
        return None
    attribution = _pick_leg_attribution(
        rule_evidence,
        exit_kind=exit_kind,
        locked_profile=locked_profile,
        bar_index=bar_index,
        aggregate_ratio=ratio,
    )
    if attribution is None:
        # A configured, computable ratio with no matching rule in
        # rule_evidence would be an internal inconsistency, not a valid
        # "no rule configured" case (that's ratio is None, handled
        # above) -- fail loudly rather than silently emit an
        # unattributed leg.
        raise AssertionError(
            "resolved protection ratio has no matching rule_evidence entry",
        )
    return InitialProtectionLeg(ratio=ratio, attribution=attribution)


def _entry_opportunities(
    evaluation: EmaPullbackEvaluation,
    bar_count: int,
) -> tuple[ExecutableEntryOpportunity, ...]:
    entries_by_side = {item.side: item.entry_allowed for item in evaluation.entries}
    exit_policy = evaluation.exit_policy
    rule_evidence = exit_policy.rule_evidence

    per_side = (
        (
            "long",
            entries_by_side.get("long", tuple(False for _ in range(bar_count))),
            exit_policy.stop_ready_long,
            exit_policy.profile_long,
            exit_policy.stop_loss_ratio_long,
            exit_policy.take_profit_ratio_long,
        ),
        (
            "short",
            entries_by_side.get("short", tuple(False for _ in range(bar_count))),
            exit_policy.stop_ready_short,
            exit_policy.profile_short,
            exit_policy.stop_loss_ratio_short,
            exit_policy.take_profit_ratio_short,
        ),
    )

    opportunities: list[ExecutableEntryOpportunity] = []
    for side, entries, protection_ready, profile_series, sl_ratio, tp_ratio in per_side:
        for i in range(bar_count):
            if not entries[i] or not protection_ready[i]:
                continue
            locked_profile = profile_series[i]
            initial_stop = _leg(
                rule_evidence,
                exit_kind="stop_loss",
                locked_profile=locked_profile,
                bar_index=i,
                ratio=sl_ratio[i],
            )
            initial_take = _leg(
                rule_evidence,
                exit_kind="take_profit",
                locked_profile=locked_profile,
                bar_index=i,
                ratio=tp_ratio[i],
            )
            opportunities.append(
                ExecutableEntryOpportunity(
                    bar_index=i,
                    side=side,  # type: ignore[arg-type]
                    locked_exit_profile=locked_profile,
                    initial_stop=initial_stop,
                    initial_take=initial_take,
                )
            )
    return tuple(opportunities)


def _signal_exit_projection(evaluation: EmaPullbackEvaluation) -> SignalExitProjection:
    exit_policy = evaluation.exit_policy
    rule_evidence = exit_policy.rule_evidence

    def build_side(
        side: Literal["long", "short"], signal_by_profile: dict[str, tuple[bool, ...]]
    ) -> dict[str, tuple[SignalExitEvent, ...]]:
        result: dict[str, tuple[SignalExitEvent, ...]] = {}
        for profile, series in signal_by_profile.items():
            profile_rules = [
                rule
                for rule in rule_evidence
                if rule.exit_kind == "signal"
                and rule.side == side
                and rule.group in ("always_on", profile)
                and rule.signal is not None
            ]
            events: list[SignalExitEvent] = []
            for i, fired in enumerate(series):
                if not fired:
                    continue
                candidates = tuple(
                    SignalExitCandidate(
                        attribution=ExitAttribution(
                            rule_id=rule.instance_id,
                            component_id=rule.component_id,
                            exit_kind="signal",
                        )
                    )
                    for rule in profile_rules
                    if rule.signal is not None and rule.signal[i]
                )
                if candidates:
                    events.append(SignalExitEvent(bar_index=i, candidates=candidates))
            result[profile] = tuple(events)
        return result

    return SignalExitProjection(
        long=build_side("long", exit_policy.signal_by_profile_long),
        short=build_side("short", exit_policy.signal_by_profile_short),
    )


def build_historical_execution_projection(
    *,
    strategy_id: str,
    config_hash: str,
    market: MarketStream,
    requested_range: TimeRange,
    market_data_hash: str,
    bar_count: int,
    evaluation: EmaPullbackEvaluation,
) -> HistoricalExecutionProjection:
    return HistoricalExecutionProjection(
        strategy_id=strategy_id,
        config_hash=config_hash,
        market=market,
        requested_range=requested_range,
        market_data_hash=market_data_hash,
        bar_count=bar_count,
        entry_opportunities=_entry_opportunities(evaluation, bar_count),
        signal_exit_events=_signal_exit_projection(evaluation),
        warnings=(
            "managed exit policy is available through /v1/strategy-evaluations/managed-replay",
        ),
    )
