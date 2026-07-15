from __future__ import annotations

import pytest

from research.experiments.config_loader import load_strategy_config
from research.strategies.ema_pullback.phase_rule_conditions.params import (
    AdxDiThresholdConditionParams,
    BarsInTradeConditionParams,
    MfeAtrConditionParams,
)
from research.strategies.ema_pullback.phase_rule_conditions.registry import (
    LEGACY_PHASE_CONDITION_TYPE_ERROR,
    PhaseRuleEvaluationContext,
    evaluate_phase_rule_condition,
    parse_phase_rule_condition,
)
from research.strategies.ema_pullback.execution.trade_runtime import TradeRuntimeState
from tests.phase_rule_test_helpers import make_phase_rule
from tests.test_exit_management_contracts import _fixture_payload, _trade_management


def _long_state(**overrides: object) -> TradeRuntimeState:
    base = TradeRuntimeState(
        trade_id="L1",
        side="long",
        entry_idx=0,
        entry_time_ms=0,
        entry_price=100.0,
        bars_in_trade=3,
        phase="initial_risk",
        max_phase_reached="initial_risk",
        best_price=106.0,
        worst_price=99.0,
        mfe_price=106.0,
        mfe_pct=0.06,
        mae_price=99.0,
        mae_pct=0.01,
        active_stop_price=None,
        active_stop_source=None,
        initial_stop_price=None,
        initial_take_profit_price=None,
        locked_exit_profile=None,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_parse_mfe_atr_component() -> None:
    cond = parse_phase_rule_condition(
        "mfe_atr",
        {"threshold": 1.0, "atr": {"timeframe": "base", "period": 14}},
    )
    assert cond.component_id == "mfe_atr"
    assert isinstance(cond.params, MfeAtrConditionParams)
    assert cond.params.threshold == 1.0


def test_parse_adx_di_threshold_component() -> None:
    cond = parse_phase_rule_condition(
        "adx_di_threshold",
        {
            "timeframe": "base",
            "period": 14,
            "adx_threshold": 40,
            "require_di_alignment": True,
        },
    )
    assert cond.component_id == "adx_di_threshold"
    assert isinstance(cond.params, AdxDiThresholdConditionParams)
    assert cond.params.adx_threshold == 40


def test_bars_in_trade_rejects_non_integer_threshold() -> None:
    with pytest.raises(ValueError, match="integer >= 1"):
        parse_phase_rule_condition("bars_in_trade", {"threshold": 1.5})


def test_unknown_component_id_rejected() -> None:
    with pytest.raises(ValueError, match="unknown phase_rules condition.component_id"):
        parse_phase_rule_condition("unknown_phase_condition", {"threshold": 1})


def test_legacy_condition_type_rejected_on_load() -> None:
    payload = _fixture_payload()
    _trade_management(payload)["exit_management"] = {
        "mode": "diagnostic_only",
        "phase_rules": [
            {
                "rule_id": "legacy",
                "to_phase": "proven",
                "condition": {"type": "mfe_atr", "threshold": 1.0},
            }
        ],
        "stop_management": [],
        "take_management": [],
        "runtime_exits": [],
    }
    with pytest.raises(ValueError, match=LEGACY_PHASE_CONDITION_TYPE_ERROR):
        load_strategy_config(payload)


def test_adx_di_threshold_long_aligned() -> None:
    import pandas as pd

    rule = make_phase_rule(
        "protected_adx",
        "protected",
        "adx_di_threshold",
        {
            "timeframe": "base",
            "period": 14,
            "adx_threshold": 40,
            "require_di_alignment": True,
        },
    )
    idx = pd.RangeIndex(3)
    ctx = PhaseRuleEvaluationContext(
        atr_series_by_key={},
        adx_dmi_series_by_key={
            ("base", 14): {
                "adx": pd.Series([30.0, 35.0, 42.0], index=idx),
                "di_plus": pd.Series([20.0, 25.0, 31.0], index=idx),
                "di_minus": pd.Series([22.0, 20.0, 18.0], index=idx),
            }
        },
    )
    result = evaluate_phase_rule_condition(
        _long_state(),
        rule.condition,
        bar_index=2,
        eval_context=ctx,
    )
    assert result.met is True
    assert result.diagnostics["di_aligned"] is True


def test_adx_di_threshold_opposing_di_for_long() -> None:
    import pandas as pd

    rule = make_phase_rule(
        "protected_adx",
        "protected",
        "adx_di_threshold",
        {
            "timeframe": "base",
            "period": 14,
            "adx_threshold": 40,
            "require_di_alignment": True,
        },
    )
    idx = pd.RangeIndex(1)
    ctx = PhaseRuleEvaluationContext(
        atr_series_by_key={},
        adx_dmi_series_by_key={
            ("base", 14): {
                "adx": pd.Series([45.0], index=idx),
                "di_plus": pd.Series([15.0], index=idx),
                "di_minus": pd.Series([28.0], index=idx),
            }
        },
    )
    result = evaluate_phase_rule_condition(
        _long_state(),
        rule.condition,
        bar_index=0,
        eval_context=ctx,
    )
    assert result.met is False
