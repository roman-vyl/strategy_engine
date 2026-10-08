"""Pure EMA Pullback evaluation over an already-built feature frame."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.indicators.contracts import FeatureFrameLike, NativeFeatureFrame
from strategy_engine.indicators.evaluation_context import EvaluationContext
from strategy_engine.strategies.contracts import LiveStrategySpec
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
    GateIdentity,
    build_context_consumption_evidence,
    resolve_context_consumption,
)
from strategy_engine.strategies.ema_pullback.contexts import (
    ContextBundle,
    build_context_bundle,
    resolve_context_bundle,
)
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    SideDirectionBlockerIdentity,
    SideDirectionBlockers,
    evaluate_direction_and_blockers,
    resolve_direction_and_blockers,
)
from strategy_engine.strategies.ema_pullback.exits import (
    ExitPolicyEvaluation,
    ExitPolicyIdentity,
    evaluate_exit_policy,
    exit_policy_consumptions,
    resolve_exit_policy,
    resolve_memoized_exit_policy,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    EmaPullbackFeaturePlan,
    resolve_feature_identities,
)
from strategy_engine.strategies.ema_pullback.managed_composite import (
    ManagedPredicateIdentities,
    has_managed_predicates,
    managed_predicate_consumptions,
    resolve_managed_predicates,
)
from strategy_engine.strategies.ema_pullback.potential_entries import (
    PotentialEntry,
    project_potential_entries,
)
from strategy_engine.strategies.ema_pullback.risk import (
    SideEntryEvaluation,
    evaluate_risk_and_entries,
)
from strategy_engine.strategies.ema_pullback.setups import (
    SideSetupEvaluation,
    SideSetupIdentity,
    evaluate_setups,
    resolve_setups,
)
from strategy_engine.strategies.ema_pullback.stack_episode import (
    build_episode_bundle,
    resolve_episode_identities,
)
from strategy_engine.strategies.ema_pullback.triggers import (
    SideTriggerEvaluation,
    SideTriggerIdentity,
    evaluate_triggers,
    resolve_triggers,
)


@dataclass(frozen=True, slots=True)
class EmaPullbackEvaluation:
    contexts: ContextBundle
    consumption: tuple[ContextConsumptionRecord, ...]
    direction_blockers: tuple[SideDirectionBlockers, ...]
    setups: tuple[SideSetupEvaluation, ...]
    triggers: tuple[SideTriggerEvaluation, ...]
    entries: tuple[SideEntryEvaluation, ...]
    exit_policy: ExitPolicyEvaluation
    potential_entries: dict[str, PotentialEntry]


def evaluate_ema_pullback_frame(
    strategy: LiveStrategySpec,
    frame: FeatureFrameLike,
    planned: EmaPullbackFeaturePlan,
    *,
    context: EvaluationContext | None = None,
) -> EmaPullbackEvaluation:
    """`context` (batch-computation-reuse 4.6): the request's
    `EvaluationContext` (range-batch or single-spec); when given, and
    `frame` is a native frame over that context's market,
    direction/blocker/setup/trigger nodes (and the mask compositions of
    those stages; 4.6) and exit-rule / per-profile
    aggregate / profile-select nodes (4.7) are memoized by identity."""

    memo = _memo_identities(strategy.raw_spec, frame, planned, context)
    memo_context = context if memo is not None else None
    contexts = build_context_bundle(strategy.raw_spec, frame, planned)
    episodes = build_episode_bundle(
        strategy.raw_spec,
        frame,
        planned.episode_columns_by_ref,
        context=memo_context,
        identities=memo.episodes if memo else None,
    )
    if episodes is not None:
        contexts = replace(contexts, episodes=episodes)
    consumption = build_context_consumption_evidence(strategy.raw_spec, contexts)
    direction_blockers = evaluate_direction_and_blockers(
        strategy.raw_spec,
        frame,
        planned,
        consumption,
        context=memo_context,
        identities=memo.direction_blockers if memo else None,
    )
    setups = evaluate_setups(
        strategy.raw_spec,
        frame,
        planned,
        consumption,
        direction_blockers,
        context=memo_context,
        identities=memo.setups if memo else None,
        bundle=contexts,
    )
    triggers = evaluate_triggers(
        strategy.raw_spec,
        frame,
        planned,
        setups,
        context=memo_context,
        identities=memo.triggers if memo else None,
    )
    entries = evaluate_risk_and_entries(strategy.raw_spec, triggers)
    exit_policy = evaluate_exit_policy(
        strategy.raw_spec,
        frame,
        planned,
        consumption,
        context=memo_context,
        identities=memo.exit_policy if memo else None,
    )
    potential_entries = project_potential_entries(
        frame,
        planned,
        setups,
        triggers,
        exit_policy,
    )
    return EmaPullbackEvaluation(
        contexts=contexts,
        consumption=consumption,
        direction_blockers=direction_blockers,
        setups=setups,
        triggers=triggers,
        entries=entries,
        exit_policy=exit_policy,
        potential_entries=potential_entries,
    )


@dataclass(frozen=True, slots=True)
class EmaPullbackIdentity:
    """Semantic node identities (batch-computation-reuse group 3) for one
    strategy spec over one market, mirroring `EmaPullbackEvaluation`.

    Resolution only -- nothing here computes, caches or skips anything, and
    `evaluate_ema_pullback_frame` does not consult it. Risk/entries and
    potential entries are outside this stage's node families."""

    features: dict[str, NodeSpec]
    contexts: dict[str, NodeSpec]
    gates: tuple[GateIdentity, ...]
    direction_blockers: tuple[SideDirectionBlockerIdentity, ...]
    setups: tuple[SideSetupIdentity, ...]
    triggers: tuple[SideTriggerIdentity, ...]
    exit_policy: ExitPolicyIdentity


def resolve_ema_pullback_frame(
    raw_spec: Mapping[str, Any],
    planned: EmaPullbackFeaturePlan,
    *,
    base_timeframe: str,
) -> EmaPullbackIdentity:
    """Identity twin of `evaluate_ema_pullback_frame`: same stages, same
    order, same shared normalization helpers, no market data read.
    `base_timeframe` is the evaluated market's base timeframe (it resolves
    the "base" timeframe alias); the market/range itself is the scope these
    identities live under, not part of them."""

    features = resolve_feature_identities(planned, base_timeframe=base_timeframe)
    contexts = resolve_context_bundle(raw_spec, planned, features)
    gates = resolve_context_consumption(raw_spec, contexts)
    direction_blockers = resolve_direction_and_blockers(raw_spec, planned, features, gates)
    setups = resolve_setups(raw_spec, planned, features, gates, direction_blockers, contexts)
    triggers = resolve_triggers(raw_spec, planned, features, setups)
    exit_policy = resolve_exit_policy(raw_spec, planned, features, contexts)
    return EmaPullbackIdentity(
        features=features,
        contexts=contexts,
        gates=gates,
        direction_blockers=direction_blockers,
        setups=setups,
        triggers=triggers,
        exit_policy=exit_policy,
    )


# -- memoized strategy nodes (batch-computation-reuse 4.6, 4.7) -------------------


@dataclass(frozen=True, slots=True)
class MemoizedStageIdentities:
    """Identities of the memoized direction/blocker, setup, trigger and
    exit-policy stages of one strategy evaluation. A stage whose identities could not be
    resolved is `None` (and so is every later stage): its nodes then compute
    directly, unmemoized, and raise exactly what they raise today."""

    direction_blockers: tuple[SideDirectionBlockerIdentity, ...] | None
    setups: tuple[SideSetupIdentity, ...] | None
    triggers: tuple[SideTriggerIdentity, ...] | None
    exit_policy: ExitPolicyIdentity | None = None
    # Predicate children of composite phase conditions, consumed by the
    # managed projection (composite-managed-phase-condition-v1 design D8);
    # empty for every spec without one.
    managed: ManagedPredicateIdentities | None = None
    # EMA stack episode nodes by `episode_identity_key`, consumed once each
    # when the episode bundle is built (ema-stack-episode-v1); empty for
    # every spec without `ema_stack_episode`.
    episodes: Mapping[str, NodeSpec] | None = None


def resolve_memoized_stages(
    raw_spec: Mapping[str, Any],
    planned: EmaPullbackFeaturePlan,
    *,
    base_timeframe: str,
) -> MemoizedStageIdentities:
    """The single resolution both the batch refcount pre-pass and the
    evaluation itself use (so prediction and consumption agree by
    construction). Pure; never raises: resolution stops at the first stage
    that cannot be resolved (that candidate's real evaluation will raise on
    its own at or before that stage)."""

    try:
        features = resolve_feature_identities(planned, base_timeframe=base_timeframe)
        episodes = resolve_episode_identities(raw_spec, planned.episode_columns_by_ref, features)
    except Exception:
        return MemoizedStageIdentities(None, None, None)
    stages = _resolve_memoized_stages(raw_spec, planned, features)
    return replace(stages, episodes=episodes) if episodes else stages


def _resolve_memoized_stages(
    raw_spec: Mapping[str, Any],
    planned: EmaPullbackFeaturePlan,
    features: Mapping[str, NodeSpec],
) -> MemoizedStageIdentities:
    try:
        contexts = resolve_context_bundle(raw_spec, planned, features)
        gates = resolve_context_consumption(raw_spec, contexts)
        direction_blockers = resolve_direction_and_blockers(raw_spec, planned, features, gates)
    except Exception:
        return MemoizedStageIdentities(None, None, None)
    try:
        setups = resolve_setups(
            raw_spec, planned, features, gates, direction_blockers, contexts
        )
    except Exception:
        return MemoizedStageIdentities(direction_blockers, None, None)
    try:
        triggers = resolve_triggers(raw_spec, planned, features, setups)
    except Exception:
        return MemoizedStageIdentities(direction_blockers, setups, None)
    try:
        exit_policy = resolve_memoized_exit_policy(raw_spec, planned, features, contexts)
    except Exception:
        return MemoizedStageIdentities(direction_blockers, setups, triggers, None)
    try:
        managed = resolve_managed_predicates(raw_spec, features, contexts)
    except Exception:
        return MemoizedStageIdentities(direction_blockers, setups, triggers, exit_policy, None)
    return MemoizedStageIdentities(direction_blockers, setups, triggers, exit_policy, managed)


def memoized_stage_consumptions(stages: MemoizedStageIdentities) -> tuple[NodeSpec, ...]:
    """Every memo consumption `evaluate_ema_pullback_frame` makes for these
    stages, in evaluation order (design.md D5 pre-pass). The width prefix is
    consumed from inside its setup's compute, so it is predicted once per
    setup consumption; when that setup is served from the memo the prefix
    consumption does not happen and the root releases it on exit."""

    consumed: list[NodeSpec] = list((stages.episodes or {}).values())
    for side in stages.direction_blockers or ():
        consumed.append(side.direction)
        for (_, intrinsic), (_, allowed) in zip(
            side.blocker_intrinsic, side.blocker_allowed, strict=True
        ):
            consumed += (intrinsic, allowed)
        consumed += (side.blockers_ok, side.pre_setup_allowed)
    for side_setups in stages.setups or ():
        for setup in side_setups.setups:
            consumed.append(setup.local)
            if setup.width_prefix is not None:
                consumed.append(setup.width_prefix)
            # A composite consumes its children from inside its own compute
            # (like the width prefix): predicted per composite consumption,
            # released by the root when the composite is served from memo.
            for child in setup.children:
                consumed.append(child.local)
                if child.width_prefix is not None:
                    consumed.append(child.width_prefix)
                if child.predicate is not None:
                    consumed += child.predicate.nested
            consumed.append(setup.final)
        consumed += (side_setups.setups_ok, side_setups.pre_trigger_allowed)
    for side_trigger in stages.triggers or ():
        consumed += (side_trigger.trigger, side_trigger.pre_risk_entry_allowed)
    if stages.exit_policy is not None:
        consumed += exit_policy_consumptions(stages.exit_policy)
    if stages.managed is not None:
        consumed += managed_predicate_consumptions(stages.managed)
    return tuple(consumed)


def _memo_identities(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrameLike,
    planned: EmaPullbackFeaturePlan,
    context: EvaluationContext | None,
) -> MemoizedStageIdentities | None:
    """Stage identities to memoize this evaluation under, or `None`.

    Only a native frame whose shared market arrays are the context's own
    (i.e. a frame evaluated over the context's exact market frame) is ever
    memoized: identities are scoped to that market range, and a boxed
    (string-serialized) frame's values are not the native values the memo
    holds."""

    if not _memoizable(frame, context):
        return None
    assert isinstance(frame, NativeFeatureFrame)
    return resolve_memoized_stages(raw_spec, planned, base_timeframe=frame.market.base_timeframe)


def _memoizable(frame: FeatureFrameLike, context: EvaluationContext | None) -> bool:
    return not (
        context is None
        or not isinstance(frame, NativeFeatureFrame)
        or frame.market_arrays is None
        or frame.market_arrays is not context.market_arrays
    )


def managed_memo_identities(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrameLike,
    planned: EmaPullbackFeaturePlan,
    context: EvaluationContext | None,
) -> ManagedPredicateIdentities | None:
    """The managed stage for the projection under the same gate as
    `_memo_identities`, resolved by the same `resolve_managed_predicates`
    the pre-pass uses. `None` (no memo) when the gate fails, when no
    composite phase condition has a predicate child -- then nothing is
    resolved at all -- or when resolution fails."""

    if not _memoizable(frame, context) or not has_managed_predicates(raw_spec):
        return None
    assert isinstance(frame, NativeFeatureFrame)
    try:
        features = resolve_feature_identities(planned, base_timeframe=frame.market.base_timeframe)
        contexts = resolve_context_bundle(raw_spec, planned, features)
        return resolve_managed_predicates(raw_spec, features, contexts)
    except Exception:
        return None
