"""Pure EMA Pullback evaluation over an already-built feature frame."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.indicators.contracts import FeatureFrameLike
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
    resolve_exit_policy,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    EmaPullbackFeaturePlan,
    resolve_feature_identities,
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
) -> EmaPullbackEvaluation:
    contexts = build_context_bundle(strategy.raw_spec, frame, planned)
    consumption = build_context_consumption_evidence(strategy.raw_spec, contexts)
    direction_blockers = evaluate_direction_and_blockers(
        strategy.raw_spec, frame, planned, consumption
    )
    setups = evaluate_setups(
        strategy.raw_spec,
        frame,
        planned,
        consumption,
        direction_blockers,
    )
    triggers = evaluate_triggers(strategy.raw_spec, frame, planned, setups)
    entries = evaluate_risk_and_entries(strategy.raw_spec, triggers)
    exit_policy = evaluate_exit_policy(strategy.raw_spec, frame, planned, consumption)
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
    setups = resolve_setups(raw_spec, planned, features, gates, direction_blockers)
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
