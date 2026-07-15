"""Validate context_consumption on strategy specs and parsed instance JSON."""

from __future__ import annotations

from typing import Any

from research.strategies.ema_pullback.components.registry import (
    COUNTER_CANDLE_BLOCKER_COMPONENT,
    EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
    NO_BLOCKERS_COMPONENT,
    RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT,
    UNTOUCHED_ANCHOR_SETUP_COMPONENT,
)

_BLOCKER_COMPONENTS_WITH_CONTEXT_CONSUMPTION = frozenset(
    {
        COUNTER_CANDLE_BLOCKER_COMPONENT,
        RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT,
    }
)
from research.strategies.ema_pullback.context.policies import HTF_REGIME_GATE_POLICY
from research.strategies.ema_pullback.spec import BlockerRuleSpec, SetupRuleSpec

HTF_REGIME_VALUES = frozenset({"aligned", "countertrend", "neutral"})

_BLOCKER_CONTEXT_POLICIES = frozenset({HTF_REGIME_GATE_POLICY})
_SETUP_CONTEXT_POLICIES = frozenset({HTF_REGIME_GATE_POLICY})
_SETUP_COMPONENTS_WITH_CONTEXT_CONSUMPTION = frozenset(
    {
        UNTOUCHED_ANCHOR_SETUP_COMPONENT,
        EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
    }
)


def validate_htf_regime_gate_params(
    params: dict[str, Any],
    *,
    path: str,
) -> None:
    if "allowed_regimes" not in params:
        raise ValueError(f"{path}.params.allowed_regimes is required for htf_regime_gate")
    raw = params["allowed_regimes"]
    if not isinstance(raw, list):
        raise ValueError(f"{path}.params.allowed_regimes must be a list of strings")
    if not raw:
        raise ValueError(f"{path}.params.allowed_regimes must be a non-empty list")
    regimes = [str(item) for item in raw]
    unknown = set(regimes) - HTF_REGIME_VALUES
    if unknown:
        raise ValueError(
            f"{path}.params.allowed_regimes has invalid values: {sorted(unknown)}"
        )


def validate_blocker_context_consumption(rule: BlockerRuleSpec) -> None:
    consumption = rule.context_consumption
    if consumption is None:
        return
    path = f"blockers[{rule.instance_id!r}].context_consumption"
    if rule.component_id == NO_BLOCKERS_COMPONENT:
        raise ValueError(
            f"{path} is not supported for component_id {rule.component_id!r}"
        )
    if rule.component_id not in _BLOCKER_COMPONENTS_WITH_CONTEXT_CONSUMPTION:
        raise ValueError(
            f"{path} is not supported for component_id {rule.component_id!r}; "
            f"supported blockers: {sorted(_BLOCKER_COMPONENTS_WITH_CONTEXT_CONSUMPTION)}"
        )
    if consumption.policy.policy_id not in _BLOCKER_CONTEXT_POLICIES:
        allowed = ", ".join(repr(item) for item in sorted(_BLOCKER_CONTEXT_POLICIES))
        raise ValueError(
            f"{path}.policy.policy_id must be one of: {allowed}; "
            f"got {consumption.policy.policy_id!r}"
        )
    validate_htf_regime_gate_params(
        dict(consumption.policy.params),
        path=f"{path}.policy",
    )


def validate_setup_context_consumption(rule: SetupRuleSpec) -> None:
    consumption = rule.context_consumption
    if consumption is None:
        return
    path = f"setups[{rule.instance_id!r}].context_consumption"
    if rule.component_id not in _SETUP_COMPONENTS_WITH_CONTEXT_CONSUMPTION:
        raise ValueError(
            f"{path} is not supported for component_id {rule.component_id!r}; "
            f"supported setups: {sorted(_SETUP_COMPONENTS_WITH_CONTEXT_CONSUMPTION)}"
        )
    if consumption.policy.policy_id not in _SETUP_CONTEXT_POLICIES:
        allowed = ", ".join(repr(item) for item in sorted(_SETUP_CONTEXT_POLICIES))
        raise ValueError(
            f"{path}.policy.policy_id must be one of: {allowed}; "
            f"got {consumption.policy.policy_id!r}"
        )
    validate_htf_regime_gate_params(
        dict(consumption.policy.params),
        path=f"{path}.policy",
    )
