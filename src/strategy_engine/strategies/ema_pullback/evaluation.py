"""Pure EMA Pullback evaluation over an already-built FeatureFrame."""

from __future__ import annotations

from dataclasses import dataclass

from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.contracts import StrategySpecEnvelope
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
    build_context_consumption_evidence,
)
from strategy_engine.strategies.ema_pullback.contexts import ContextBundle, build_context_bundle
from strategy_engine.strategies.ema_pullback.direction_blockers import (
    SideDirectionBlockers,
    evaluate_direction_and_blockers,
)
from strategy_engine.strategies.ema_pullback.exits import ExitPolicyEvaluation, evaluate_exit_policy
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.potential_entries import (
    PotentialEntry,
    project_potential_entries,
)
from strategy_engine.strategies.ema_pullback.risk import (
    SideEntryEvaluation,
    evaluate_risk_and_entries,
)
from strategy_engine.strategies.ema_pullback.setups import SideSetupEvaluation, evaluate_setups
from strategy_engine.strategies.ema_pullback.triggers import (
    SideTriggerEvaluation,
    evaluate_triggers,
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
    strategy: StrategySpecEnvelope,
    frame: FeatureFrame,
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
