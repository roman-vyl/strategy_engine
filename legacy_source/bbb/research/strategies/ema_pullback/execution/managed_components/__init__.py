"""Managed exit_management component evaluators (v2 role-family).

Distinct from ``components/`` catalog roles (setup, blocker, trigger, exit_policy).
These evaluators accompany an already-open trade during the managed bar-by-bar loop.
"""

from research.strategies.ema_pullback.execution.managed_components.activation import (
    phase_at_least_met,
)
from research.strategies.ema_pullback.execution.managed_components.runtime_exit import (
    evaluate_runtime_exits,
)
from research.strategies.ema_pullback.execution.managed_components.snapshot import (
    ManagementEvaluationResult,
    evaluate_management_layers,
)
from research.strategies.ema_pullback.execution.managed_components.stop import (
    apply_tighten_only_stop,
    evaluate_break_even_stop,
    evaluate_lock_profit_stop,
    evaluate_stop_management,
    merge_stop_candidates,
)
from research.strategies.ema_pullback.execution.managed_components.take import (
    evaluate_take_management,
    take_profile_descriptor,
)

__all__ = [
    "ManagementEvaluationResult",
    "apply_tighten_only_stop",
    "evaluate_break_even_stop",
    "evaluate_lock_profit_stop",
    "evaluate_management_layers",
    "evaluate_runtime_exits",
    "evaluate_stop_management",
    "evaluate_take_management",
    "merge_stop_candidates",
    "phase_at_least_met",
    "take_profile_descriptor",
]
