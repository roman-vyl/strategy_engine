"""Allowlisted phase-rule condition registry: validate, plan features, evaluate."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from research.strategies.ema_pullback.phase_rule_conditions.params import (
    AdxDiThresholdConditionParams,
    BarsInTradeConditionParams,
    MfeAtrConditionParams,
    MfePctConditionParams,
    PHASE_RULE_CONDITION_COMPONENT_IDS,
    PhaseRuleAtrSpec,
    PhaseRuleConditionParams,
)
from research.strategies.ema_pullback.spec import PhaseRuleConditionSpec

LEGACY_PHASE_CONDITION_TYPE_ERROR = (
    "unsupported legacy phase_rules condition.type; "
    "use condition.component_id and params"
)


@dataclass(frozen=True)
class PhaseRuleEvaluationContext:
    atr_series_by_key: dict[tuple[str, int], pd.Series]
    adx_dmi_series_by_key: dict[tuple[str, int], dict[str, pd.Series]]


@dataclass(frozen=True)
class PhaseRuleEvaluationResult:
    met: bool
    diagnostics: dict[str, Any]


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _require_positive_float(raw: Any, *, path: str) -> float:
    value = _finite_float(raw)
    if value is None or value <= 0:
        raise ValueError(f"{path} must be a positive number")
    return value


def _require_positive_int(raw: Any, *, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        try:
            if isinstance(raw, float) and raw.is_integer():
                raw = int(raw)
            else:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"{path} must be an integer >= 1") from None
    if raw < 1:
        raise ValueError(f"{path} must be an integer >= 1")
    return raw


def _parse_atr_ref(raw: Any, *, path: str) -> PhaseRuleAtrSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be an object with timeframe and period")
    timeframe = str(raw.get("timeframe") or "").strip()
    if not timeframe:
        raise ValueError(f"{path}.timeframe must be non-empty")
    period = _require_positive_int(raw.get("period"), path=f"{path}.period")
    return PhaseRuleAtrSpec(timeframe=timeframe, period=period)


def _validate_mfe_atr_params(raw: Any, *, path: str) -> MfeAtrConditionParams:
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be an object")
    threshold = _require_positive_float(raw.get("threshold"), path=f"{path}.threshold")
    atr = _parse_atr_ref(raw.get("atr"), path=f"{path}.atr")
    return MfeAtrConditionParams(threshold=threshold, atr=atr)


def _validate_mfe_pct_params(raw: Any, *, path: str) -> MfePctConditionParams:
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be an object")
    threshold = _require_positive_float(raw.get("threshold"), path=f"{path}.threshold")
    return MfePctConditionParams(threshold=threshold)


def _validate_bars_in_trade_params(raw: Any, *, path: str) -> BarsInTradeConditionParams:
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be an object")
    threshold = _require_positive_int(raw.get("threshold"), path=f"{path}.threshold")
    return BarsInTradeConditionParams(threshold=threshold)


def _validate_adx_di_threshold_params(raw: Any, *, path: str) -> AdxDiThresholdConditionParams:
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be an object")
    timeframe = str(raw.get("timeframe") or "").strip()
    if not timeframe:
        raise ValueError(f"{path}.timeframe must be non-empty")
    period = _require_positive_int(raw.get("period"), path=f"{path}.period")
    adx_threshold = _require_positive_float(
        raw.get("adx_threshold"),
        path=f"{path}.adx_threshold",
    )
    require_raw = raw.get("require_di_alignment", True)
    if not isinstance(require_raw, bool):
        raise ValueError(f"{path}.require_di_alignment must be a boolean")
    return AdxDiThresholdConditionParams(
        timeframe=timeframe,
        period=period,
        adx_threshold=adx_threshold,
        require_di_alignment=require_raw,
    )


_VALIDATORS: dict[str, Callable[..., PhaseRuleConditionParams]] = {
    "mfe_atr": _validate_mfe_atr_params,
    "mfe_pct": _validate_mfe_pct_params,
    "bars_in_trade": _validate_bars_in_trade_params,
    "adx_di_threshold": _validate_adx_di_threshold_params,
}


def parse_phase_rule_condition(
    component_id: str,
    params: Any,
    *,
    path: str = "condition.params",
) -> PhaseRuleConditionSpec:
    cid = str(component_id or "").strip()
    if cid not in PHASE_RULE_CONDITION_COMPONENT_IDS:
        allowed = ", ".join(repr(item) for item in PHASE_RULE_CONDITION_COMPONENT_IDS)
        raise ValueError(f"unknown phase_rules condition.component_id {component_id!r}; allowed: {allowed}")
    validator = _VALIDATORS[cid]
    typed_params = validator(params, path=path)
    return PhaseRuleConditionSpec(component_id=cid, params=typed_params)


def _evaluate_mfe_atr(
    state: Any,
    params: MfeAtrConditionParams,
    *,
    bar_index: int,
    eval_context: PhaseRuleEvaluationContext,
) -> PhaseRuleEvaluationResult:
    key = (params.atr.timeframe, params.atr.period)
    atr_series = eval_context.atr_series_by_key.get(key)
    if atr_series is None or not (0 <= bar_index < len(atr_series)):
        return PhaseRuleEvaluationResult(met=False, diagnostics={"reason": "indicator_not_ready"})
    atr_value = _finite_float(atr_series.iloc[bar_index])
    if atr_value is None or atr_value <= 0:
        return PhaseRuleEvaluationResult(met=False, diagnostics={"reason": "indicator_not_ready"})
    favorable_distance = abs(state.mfe_price - state.entry_price)
    met = favorable_distance >= (params.threshold * atr_value)
    return PhaseRuleEvaluationResult(
        met=met,
        diagnostics={
            "threshold": params.threshold,
            "atr": atr_value,
            "atr_timeframe": params.atr.timeframe,
            "atr_period": params.atr.period,
        },
    )


def _evaluate_mfe_pct(
    state: Any,
    params: MfePctConditionParams,
    *,
    bar_index: int,
    eval_context: PhaseRuleEvaluationContext,
) -> PhaseRuleEvaluationResult:
    del bar_index, eval_context
    met = state.mfe_pct >= params.threshold
    return PhaseRuleEvaluationResult(met=met, diagnostics={"threshold": params.threshold})


def _evaluate_bars_in_trade(
    state: Any,
    params: BarsInTradeConditionParams,
    *,
    bar_index: int,
    eval_context: PhaseRuleEvaluationContext,
) -> PhaseRuleEvaluationResult:
    del bar_index, eval_context
    met = state.bars_in_trade >= params.threshold
    return PhaseRuleEvaluationResult(
        met=met,
        diagnostics={"threshold": params.threshold, "bars_in_trade": state.bars_in_trade},
    )


def _evaluate_adx_di_threshold(
    state: Any,
    params: AdxDiThresholdConditionParams,
    *,
    bar_index: int,
    eval_context: PhaseRuleEvaluationContext,
) -> PhaseRuleEvaluationResult:
    key = (params.timeframe, params.period)
    columns = eval_context.adx_dmi_series_by_key.get(key)
    if columns is None:
        return PhaseRuleEvaluationResult(met=False, diagnostics={"reason": "indicator_not_ready"})
    adx = _finite_float(columns["adx"].iloc[bar_index]) if "adx" in columns else None
    di_plus = _finite_float(columns["di_plus"].iloc[bar_index]) if "di_plus" in columns else None
    di_minus = _finite_float(columns["di_minus"].iloc[bar_index]) if "di_minus" in columns else None
    if adx is None or di_plus is None or di_minus is None:
        return PhaseRuleEvaluationResult(met=False, diagnostics={"reason": "indicator_not_ready"})
    if state.side == "long":
        di_aligned = di_plus > di_minus
    else:
        di_aligned = di_minus > di_plus
    met = adx >= params.adx_threshold and (
        not params.require_di_alignment or di_aligned
    )
    return PhaseRuleEvaluationResult(
        met=met,
        diagnostics={
            "adx": adx,
            "di_plus": di_plus,
            "di_minus": di_minus,
            "di_aligned": di_aligned,
            "timeframe": params.timeframe,
            "period": params.period,
            "adx_threshold": params.adx_threshold,
            "require_di_alignment": params.require_di_alignment,
        },
    )


_EVALUATORS: dict[str, Callable[..., PhaseRuleEvaluationResult]] = {
    "mfe_atr": _evaluate_mfe_atr,
    "mfe_pct": _evaluate_mfe_pct,
    "bars_in_trade": _evaluate_bars_in_trade,
    "adx_di_threshold": _evaluate_adx_di_threshold,
}


def evaluate_phase_rule_condition(
    state: Any,
    condition: PhaseRuleConditionSpec,
    *,
    bar_index: int,
    eval_context: PhaseRuleEvaluationContext,
) -> PhaseRuleEvaluationResult:
    evaluator = _EVALUATORS[condition.component_id]
    return evaluator(state, condition.params, bar_index=bar_index, eval_context=eval_context)


def plan_phase_rule_condition_features(
    condition: PhaseRuleConditionSpec,
    *,
    add_atr: Callable[[str, int], None],
    add_adx_dmi: Callable[[str, int], None],
) -> None:
    params = condition.params
    if isinstance(params, MfeAtrConditionParams):
        add_atr(params.atr.timeframe, params.atr.period)
    elif isinstance(params, AdxDiThresholdConditionParams):
        add_adx_dmi(params.timeframe, params.period)


def build_evaluation_context_from_enriched(
    enriched: pd.DataFrame,
    phase_rules: tuple[Any, ...],
) -> PhaseRuleEvaluationContext:
    atr_keys: set[tuple[str, int]] = set()
    adx_dmi_keys: set[tuple[str, int]] = set()
    for rule in phase_rules:
        params = rule.condition.params
        if isinstance(params, MfeAtrConditionParams):
            atr_keys.add((params.atr.timeframe, params.atr.period))
        elif isinstance(params, AdxDiThresholdConditionParams):
            adx_dmi_keys.add((params.timeframe, params.period))

    atr_series_by_key: dict[tuple[str, int], pd.Series] = {}
    for timeframe, period in atr_keys:
        column = f"atr_close_{timeframe}_{period}"
        if column in enriched.columns:
            atr_series_by_key[(timeframe, period)] = enriched[column].astype(float)

    adx_dmi_series_by_key: dict[tuple[str, int], dict[str, pd.Series]] = {}
    for timeframe, period in adx_dmi_keys:
        adx_col = f"adx_close_{timeframe}_{period}"
        di_plus_col = f"di_plus_close_{timeframe}_{period}"
        di_minus_col = f"di_minus_close_{timeframe}_{period}"
        if (
            adx_col in enriched.columns
            and di_plus_col in enriched.columns
            and di_minus_col in enriched.columns
        ):
            adx_dmi_series_by_key[(timeframe, period)] = {
                "adx": enriched[adx_col].astype(float),
                "di_plus": enriched[di_plus_col].astype(float),
                "di_minus": enriched[di_minus_col].astype(float),
            }

    return PhaseRuleEvaluationContext(
        atr_series_by_key=atr_series_by_key,
        adx_dmi_series_by_key=adx_dmi_series_by_key,
    )
