"""Bar-open exit candidate arbitration for execution-layer close selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from research.strategies.ema_pullback.execution.trade_runtime import ExitCandidate

SAME_BAR_POLICY_V1 = "v1"

_CANDIDATE_PRIORITY: dict[str, int] = {
    "stop_loss": 1,
    "managed_stop": 2,
    "take_profit": 3,
    "runtime_protective": 4,
    "runtime_take": 5,
    "runtime_close": 6,
    "runtime_exit": 6,
    "signal": 7,
}


def _candidate_priority(candidate: ExitCandidate) -> int:
    if candidate.candidate_type is not None:
        return _CANDIDATE_PRIORITY.get(candidate.candidate_type, 99)
    reason = candidate.reason
    if reason.startswith("stop_loss:") or reason == "stop_loss":
        return 1
    if reason.startswith("active_stop:"):
        return 2
    if reason.startswith("take_profit:") or reason == "take_profit":
        return 3
    if reason.startswith("runtime_exit:"):
        return 4
    if reason.startswith("signal:"):
        return 5
    return 99


@dataclass(frozen=True)
class ArbitrationResult:
    winner: ExitCandidate | None
    same_bar_policy: Literal["v1"] = SAME_BAR_POLICY_V1
    losing_candidates: tuple[ExitCandidate, ...] = ()


@dataclass
class ExitArbitrator:
    same_bar_policy: Literal["v1"] = SAME_BAR_POLICY_V1

    def select_winner(
        self,
        candidates: list[ExitCandidate],
        *,
        bar_index: int,
    ) -> ArbitrationResult:
        hits = [candidate for candidate in candidates if candidate.bar == bar_index]
        if not hits:
            return ArbitrationResult(winner=None, losing_candidates=())

        ordered = sorted(
            hits,
            key=lambda candidate: (_candidate_priority(candidate), candidate.reason),
        )
        winner = ordered[0]
        losers = tuple(item for item in ordered[1:])
        return ArbitrationResult(
            winner=winner,
            same_bar_policy=self.same_bar_policy,
            losing_candidates=losers,
        )


def arbitration_metadata(result: ArbitrationResult) -> dict[str, Any]:
    if result.winner is None:
        return {"same_bar_policy": result.same_bar_policy}
    return {
        "same_bar_policy": result.same_bar_policy,
        "losing_candidates": [
            {
                "layer": item.layer,
                "rule_id": item.rule_id,
                "component_id": item.component_id,
                "price": item.price,
                "reason": item.reason,
                "candidate_type": item.candidate_type,
            }
            for item in result.losing_candidates
        ],
    }
