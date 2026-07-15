from __future__ import annotations

from pathlib import Path

import pandas as pd
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


def test_direct_legacy_no_risk_and_final_composition_parity() -> None:
    root = Path(__file__).parents[1] / "legacy_source/bbb/research/strategies/ema_pullback"
    risk_path = root / "components/risk.py"
    signals_path = root / "execution/signals.py"

    # Load just the legacy risk function; its only package dependency is a type alias.
    text = risk_path.read_text().replace(
        "from research.strategies.ema_pullback.spec import TradeSide",
        "from typing import Literal\nTradeSide = Literal['long', 'short']",
    )
    namespace: dict[str, object] = {}
    exec(compile(text, str(risk_path), "exec"), namespace)
    legacy_no_risk = namespace["no_risk_filter"]

    index = pd.RangeIndex(3)
    frame = pd.DataFrame(index=index)
    legacy_risk = tuple(bool(x) for x in legacy_no_risk(frame, side="long"))
    new = evaluate_risk_and_entries(
        {"components": {"risk": "no_risk_filter"}}, trigger_inputs()[:1]
    )[0]
    assert new.risk.allowed == legacy_risk

    # Validate the legacy final formula explicitly from the copied source contract.
    assert (
        "direction_allowed & blockers_ok & setup_ok & trigger_ok & risk_ok"
        in signals_path.read_text()
    )
    assert new.entry_allowed == (True, False, True)
