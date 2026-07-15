from __future__ import annotations

from research.strategies.ema_pullback.phase_rule_conditions.registry import (
    PhaseRuleEvaluationContext,
    parse_phase_rule_condition,
)
from research.strategies.ema_pullback.spec import PhaseRuleSpec


def make_phase_rule(
    rule_id: str,
    to_phase: str,
    component_id: str,
    params: dict,
) -> PhaseRuleSpec:
    return PhaseRuleSpec(
        rule_id=rule_id,
        to_phase=to_phase,  # type: ignore[arg-type]
        condition=parse_phase_rule_condition(component_id, params),
    )


def empty_phase_eval_context() -> PhaseRuleEvaluationContext:
    return PhaseRuleEvaluationContext(atr_series_by_key={}, adx_dmi_series_by_key={})
