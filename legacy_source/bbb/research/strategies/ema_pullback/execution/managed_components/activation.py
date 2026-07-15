from __future__ import annotations

from research.strategies.ema_pullback.spec import TRADE_MANAGEMENT_PHASES


def _phase_rank(phase: str) -> int:
    return TRADE_MANAGEMENT_PHASES.index(phase)


def phase_at_least_met(current_phase: str, threshold: str) -> bool:
    return _phase_rank(current_phase) >= _phase_rank(threshold)
