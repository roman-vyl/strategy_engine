from __future__ import annotations

import ast
from pathlib import Path

import pytest

from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.strategies.live_projections.registry import (
    LiveEntryProjectionRegistry,
    OpenTradeProjectionRegistry,
)


def test_empty_registries_reject_unsupported_strategy_family() -> None:
    with pytest.raises(UnsupportedCapabilityError) as entry_error:
        LiveEntryProjectionRegistry().resolve("unknown")
    with pytest.raises(UnsupportedCapabilityError) as trade_error:
        OpenTradeProjectionRegistry().resolve("unknown")
    assert entry_error.value.details["capability"] == "strategy_live_entry:unknown"
    assert trade_error.value.details["capability"] == "strategy_open_trade:unknown"


def test_generic_live_use_cases_do_not_branch_on_ema_pullback() -> None:
    root = Path(__file__).parents[1]
    for relative in (
        "src/strategy_engine/strategies/application/evaluate_live_entry_projection.py",
        "src/strategy_engine/strategies/application/evaluate_open_trade_projection.py",
    ):
        source = (root / relative).read_text()
        tree = ast.parse(source)
        assert "ema_pullback" not in source
        assert not any(isinstance(node, ast.If) for node in ast.walk(tree))
