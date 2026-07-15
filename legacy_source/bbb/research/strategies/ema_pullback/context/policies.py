"""Consumer-owned context policies."""

from __future__ import annotations

import pandas as pd

from research.strategies.ema_pullback.spec import ContextConsumptionPolicySpec, TradeSide

EXIT_PROFILE_BY_HTF_STATE_POLICY = "exit_profile_by_htf_state"
HTF_REGIME_GATE_POLICY = "htf_regime_gate"

_STATE_ORDER = ("up", "down", "neutral")


def resolve_htf_regime(raw_state: str, side: TradeSide) -> str:
    """Single source of truth for raw HTF state + trade side -> regime."""

    if raw_state not in _STATE_ORDER:
        return "neutral"
    if side == "long":
        if raw_state == "up":
            return "aligned"
        if raw_state == "down":
            return "countertrend"
        return "neutral"
    if raw_state == "down":
        return "aligned"
    if raw_state == "up":
        return "countertrend"
    return "neutral"


def apply_exit_profile_by_htf_state(
    raw_state: pd.Series,
    *,
    policy: ContextConsumptionPolicySpec,
    index: pd.Index,
    sides: tuple[TradeSide, ...],
) -> tuple[pd.Series, pd.Series]:
    _ = policy
    context_state = raw_state.reindex(index).fillna("neutral")
    profile_long = context_state.map(
        lambda state: resolve_htf_regime(state, "long")
    ).astype("object")
    profile_short = context_state.map(
        lambda state: resolve_htf_regime(state, "short")
    ).astype("object")
    if "long" not in sides:
        profile_long = pd.Series("neutral", index=index, dtype="object")
    if "short" not in sides:
        profile_short = pd.Series("neutral", index=index, dtype="object")
    return profile_long, profile_short


def _allowed_regimes_from_policy(policy: ContextConsumptionPolicySpec) -> frozenset[str]:
    """Assumes loader/spec validation already checked allowed_regimes shape."""

    params = dict(policy.params)
    raw = params["allowed_regimes"]
    return frozenset(str(item) for item in raw)
