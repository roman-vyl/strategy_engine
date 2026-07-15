from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def legacy_stop_module():
    for name in (
        "research",
        "research.strategies",
        "research.strategies.ema_pullback",
        "research.strategies.ema_pullback.execution",
        "research.strategies.ema_pullback.execution.managed_components",
    ):
        sys.modules.setdefault(name, types.ModuleType(name))
    activation = types.ModuleType(
        "research.strategies.ema_pullback.execution.managed_components.activation"
    )
    activation.phase_at_least_met = lambda current, threshold: (
        ("initial_risk", "proven", "protected", "runner", "exhaustion").index(current)
        >= ("initial_risk", "proven", "protected", "runner", "exhaustion").index(threshold)
    )
    sys.modules[activation.__name__] = activation
    path = (
        Path(__file__).parents[1]
        / "legacy_source/bbb/research/strategies/ema_pullback/execution/managed_components/stop.py"
    )
    spec = importlib.util.spec_from_file_location("legacy_managed_stop", path)
    assert spec is not None and spec.loader is not None
    return path


def test_legacy_managed_source_is_preserved_as_parity_reference() -> None:
    path = legacy_stop_module()
    text = path.read_text()
    assert "apply_tighten_only_stop" in text
    assert "evaluate_break_even_stop" in text
    assert "evaluate_lock_profit_stop" in text
