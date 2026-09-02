"""BBB-compatible ema_pullback risk layer and final entry composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    RISK_SUPPORTED as _SUPPORTED,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    resolve_risk_component_id as _risk_component_id,
)
from strategy_engine.strategies.ema_pullback.triggers import SideTriggerEvaluation


@dataclass(frozen=True, slots=True)
class RiskMask:
    component_id: str
    side: str
    allowed: tuple[bool, ...]

    def to_wire(self) -> dict[str, object]:
        allowed_count = sum(self.allowed)
        return {
            "component_id": self.component_id,
            "side": self.side,
            "allowed": list(self.allowed),
            "counters": {
                "allowed_count": allowed_count,
                "blocked_count": len(self.allowed) - allowed_count,
            },
        }


@dataclass(frozen=True, slots=True)
class SideEntryEvaluation:
    side: str
    risk: RiskMask
    entry_allowed: tuple[bool, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "side": self.side,
            "risk": self.risk.to_wire(),
            "entry_allowed": list(self.entry_allowed),
            "entry_count": sum(self.entry_allowed),
        }


def evaluate_risk_and_entries(
    raw_spec: Mapping[str, Any],
    triggers: tuple[SideTriggerEvaluation, ...],
) -> tuple[SideEntryEvaluation, ...]:
    component_id = _risk_component_id(raw_spec)
    if component_id not in _SUPPORTED:
        raise InvalidRequestError("unsupported risk component", component_id=component_id)
    outputs: list[SideEntryEvaluation] = []
    for prior in triggers:
        risk_allowed = tuple(True for _ in prior.pre_risk_entry_allowed)
        entry_allowed = tuple(
            pre_risk and risk
            for pre_risk, risk in zip(
                prior.pre_risk_entry_allowed,
                risk_allowed,
                strict=True,
            )
        )
        outputs.append(
            SideEntryEvaluation(
                side=prior.side,
                risk=RiskMask(component_id, prior.side, risk_allowed),
                entry_allowed=entry_allowed,
            )
        )
    return tuple(outputs)
