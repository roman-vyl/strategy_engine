from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from strategy_engine.strategies.ema_pullback.context_consumption import resolve_htf_regime


@dataclass(frozen=True)
class ContextConsumptionPolicySpec:
    policy_id: str
    params: tuple[tuple[str, Any], ...] = ()


def legacy_policies():
    research = types.ModuleType("research")
    strategies = types.ModuleType("research.strategies")
    ema = types.ModuleType("research.strategies.ema_pullback")
    spec_module = types.ModuleType("research.strategies.ema_pullback.spec")
    spec_module.ContextConsumptionPolicySpec = ContextConsumptionPolicySpec
    spec_module.TradeSide = str
    sys.modules.setdefault("research", research)
    sys.modules.setdefault("research.strategies", strategies)
    sys.modules.setdefault("research.strategies.ema_pullback", ema)
    sys.modules["research.strategies.ema_pullback.spec"] = spec_module
    path = (
        Path(__file__).parents[1]
        / "legacy_source/bbb/research/strategies/ema_pullback/context/policies.py"
    )
    module_spec = importlib.util.spec_from_file_location("legacy_context_policies", path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_side_relative_resolution_matches_legacy_bbb() -> None:
    legacy = legacy_policies()
    for raw_state in ("up", "down", "neutral", "unknown"):
        for side in ("long", "short"):
            assert resolve_htf_regime(raw_state, side) == legacy.resolve_htf_regime(raw_state, side)
