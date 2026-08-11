from __future__ import annotations

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.risk import evaluate_risk_and_entries
from strategy_engine.strategies.ema_pullback.triggers import (
    SideTriggerEvaluation,
    TriggerMask,
)


def trigger_inputs() -> tuple[SideTriggerEvaluation, ...]:
    return (
        SideTriggerEvaluation(
            "long",
            TriggerMask("touch_anchor", "long", (True, False, True), {}),
            (True, False, True),
        ),
        SideTriggerEvaluation(
            "short",
            TriggerMask("touch_anchor", "short", (False, True, False), {}),
            (False, True, False),
        ),
    )


def test_no_risk_filter_preserves_pre_risk_entry_masks() -> None:
    spec = {"components": {"risk": "no_risk_filter"}}
    result = evaluate_risk_and_entries(spec, trigger_inputs())
    assert result[0].risk.allowed == (True, True, True)
    assert result[0].entry_allowed == (True, False, True)
    assert result[1].entry_allowed == (False, True, False)


def test_object_shaped_risk_component_is_supported() -> None:
    spec = {"components": {"risk": {"component_id": "no_risk_filter"}}}
    assert evaluate_risk_and_entries(spec, trigger_inputs())[0].entry_allowed == (
        True,
        False,
        True,
    )


def test_unknown_risk_component_is_rejected() -> None:
    with pytest.raises(InvalidRequestError, match="unsupported risk component"):
        evaluate_risk_and_entries({"components": {"risk": "future_risk_filter"}}, trigger_inputs())
