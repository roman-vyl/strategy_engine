"""Typed params for allowlisted phase-rule condition components."""

from __future__ import annotations

from dataclasses import dataclass

PHASE_RULE_CONDITION_COMPONENT_IDS: tuple[str, ...] = (
    "mfe_atr",
    "mfe_pct",
    "bars_in_trade",
    "adx_di_threshold",
)


@dataclass(frozen=True)
class PhaseRuleAtrSpec:
    timeframe: str = "base"
    period: int = 14

    def __post_init__(self) -> None:
        if not self.timeframe.strip():
            raise ValueError("phase_rules condition atr.timeframe must be non-empty")
        if self.period <= 0:
            raise ValueError("phase_rules condition atr.period must be > 0")


@dataclass(frozen=True)
class MfeAtrConditionParams:
    threshold: float
    atr: PhaseRuleAtrSpec


@dataclass(frozen=True)
class MfePctConditionParams:
    threshold: float


@dataclass(frozen=True)
class BarsInTradeConditionParams:
    threshold: int


@dataclass(frozen=True)
class AdxDiThresholdConditionParams:
    timeframe: str
    period: int
    adx_threshold: float
    require_di_alignment: bool = True


PhaseRuleConditionParams = (
    MfeAtrConditionParams
    | MfePctConditionParams
    | BarsInTradeConditionParams
    | AdxDiThresholdConditionParams
)
