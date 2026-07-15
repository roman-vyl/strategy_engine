"""Family-local component registry for ema_pullback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from research.strategies.ema_pullback.components.blockers import (
    counter_candle_blocker,
    no_blockers,
    rsi_lookback_extreme_blocker,
    trend_strength_episode_blocker,
)
from research.strategies.ema_pullback.components.direction import (
    ema_anchor_stack_trend,
)
from research.strategies.ema_pullback.components.exits import (
    atr_distance_exit,
    constant_usd_distance_exit,
    ema_close_loss_exit,
    ema_cross_loss_exit,
    no_signal_exit,
    rsi_signal_exit,
)
from research.strategies.ema_pullback.components.risk import no_risk_filter
from research.strategies.ema_pullback.components.setup import (
    anchor_stack_width_setup,
    ema_bounce_counter_setup,
    untouched_anchor_setup,
)
from research.strategies.ema_pullback.components.triggers import (
    reclaim_anchor,
    strong_reclaim_anchor,
    touch_anchor,
)


REQUIRED_COMPONENT_ROLES: tuple[str, ...] = (
    "direction",
    "blockers",
    "setup",
    "trigger",
    "exits",
    "risk",
)

EMA_ANCHOR_STACK_TREND_COMPONENT = "ema_anchor_stack_trend"
NO_BLOCKERS_COMPONENT = "no_blockers"
COUNTER_CANDLE_BLOCKER_COMPONENT = "counter_candle_blocker"
RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT = "rsi_lookback_extreme_blocker"
TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT = "trend_strength_episode_blocker"
UNTOUCHED_ANCHOR_SETUP_COMPONENT = "untouched_anchor_setup"
EMA_BOUNCE_COUNTER_SETUP_COMPONENT = "ema_bounce_counter_setup"
ANCHOR_STACK_WIDTH_SETUP_COMPONENT = "anchor_stack_width_setup"
RECLAIM_ANCHOR_COMPONENT = "reclaim_anchor"
STRONG_RECLAIM_ANCHOR_COMPONENT = "strong_reclaim_anchor"
TOUCH_ANCHOR_COMPONENT = "touch_anchor"
HTF_CONTEXT_COMPONENT = "htf_context"
NO_SIGNAL_EXIT_COMPONENT = "no_signal_exit"
RSI_SIGNAL_EXIT_COMPONENT = "rsi_signal_exit"
EMA_CLOSE_LOSS_EXIT_COMPONENT = "ema_close_loss_exit"
EMA_CROSS_LOSS_EXIT_COMPONENT = "ema_cross_loss_exit"
ATR_STOP_LOSS_COMPONENT = "atr_stop_loss"
ATR_TAKE_PROFIT_COMPONENT = "atr_take_profit"
CONSTANT_USD_STOP_LOSS_COMPONENT = "constant_usd_stop_loss"
CONSTANT_USD_TAKE_PROFIT_COMPONENT = "constant_usd_take_profit"
NO_RISK_FILTER_COMPONENT = "no_risk_filter"


@dataclass(frozen=True)
class ComponentDefinition:
    role: str
    component_id: str
    func: Callable[..., object]
    description: str | None = None


COMPONENT_REGISTRY: dict[str, dict[str, ComponentDefinition]] = {
    "direction": {
        EMA_ANCHOR_STACK_TREND_COMPONENT: ComponentDefinition(
            role="direction",
            component_id=EMA_ANCHOR_STACK_TREND_COMPONENT,
            func=ema_anchor_stack_trend,
            description="Allow long when fast > anchor > slow; short mirrors the stack.",
        ),
    },
    "blockers": {
        NO_BLOCKERS_COMPONENT: ComponentDefinition(
            role="blockers",
            component_id=NO_BLOCKERS_COMPONENT,
            func=no_blockers,
            description="No blocker constraints (all True).",
        ),
        COUNTER_CANDLE_BLOCKER_COMPONENT: ComponentDefinition(
            role="blockers",
            component_id=COUNTER_CANDLE_BLOCKER_COMPONENT,
            func=counter_candle_blocker,
            description="Block long on bearish candles and short on bullish candles.",
        ),
        RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT: ComponentDefinition(
            role="blockers",
            component_id=RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT,
            func=rsi_lookback_extreme_blocker,
            description=(
                "Block long after overbought RSI extreme or short after oversold "
                "extreme within lookback."
            ),
        ),
        TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT: ComponentDefinition(
            role="blockers",
            component_id=TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT,
            func=trend_strength_episode_blocker,
            description=(
                "Allow pullback entries only while a recent side-aware ADX/DMI "
                "strength episode is still active (not raw ADX on entry bar)."
            ),
        ),
    },
    "setup": {
        UNTOUCHED_ANCHOR_SETUP_COMPONENT: ComponentDefinition(
            role="setup",
            component_id=UNTOUCHED_ANCHOR_SETUP_COMPONENT,
            func=untouched_anchor_setup,
            description=(
                "Armed regime after anchor was untouched for lookback bars; "
                "active through first touch and active_bars window."
            ),
        ),
        EMA_BOUNCE_COUNTER_SETUP_COMPONENT: ComponentDefinition(
            role="setup",
            component_id=EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
            func=ema_bounce_counter_setup,
            description=(
                "Allow entries while anchor EMA bounce interactions inside a base "
                "EMA-stack trend episode have not exhausted max_bounces."
            ),
        ),
        ANCHOR_STACK_WIDTH_SETUP_COMPONENT: ComponentDefinition(
            role="setup",
            component_id=ANCHOR_STACK_WIDTH_SETUP_COMPONENT,
            func=anchor_stack_width_setup,
            description=(
                "Allow entries when fast/slow anchor stack width is sufficient on the "
                "entry bar and was expanded within the lookback window (ATR-normalized)."
            ),
        ),
    },
    "trigger": {
        RECLAIM_ANCHOR_COMPONENT: ComponentDefinition(
            role="trigger",
            component_id=RECLAIM_ANCHOR_COMPONENT,
            func=reclaim_anchor,
            description=(
                "Wick probed anchor within prior lookback bars; entry on close reclaim."
            ),
        ),
        STRONG_RECLAIM_ANCHOR_COMPONENT: ComponentDefinition(
            role="trigger",
            component_id=STRONG_RECLAIM_ANCHOR_COMPONENT,
            func=strong_reclaim_anchor,
            description=(
                "Close lost anchor within prior lookback bars; entry on close reclaim."
            ),
        ),
        TOUCH_ANCHOR_COMPONENT: ComponentDefinition(
            role="trigger",
            component_id=TOUCH_ANCHOR_COMPONENT,
            func=touch_anchor,
            description="Entry when price touches the anchor.",
        ),
    },
    "exits": {
        NO_SIGNAL_EXIT_COMPONENT: ComponentDefinition(
            role="exits",
            component_id=NO_SIGNAL_EXIT_COMPONENT,
            func=no_signal_exit,
            description="No signal-based exits.",
        ),
        RSI_SIGNAL_EXIT_COMPONENT: ComponentDefinition(
            role="exits",
            component_id=RSI_SIGNAL_EXIT_COMPONENT,
            func=rsi_signal_exit,
            description="Signal exit on side-aware RSI thresholds.",
        ),
        EMA_CLOSE_LOSS_EXIT_COMPONENT: ComponentDefinition(
            role="exits",
            component_id=EMA_CLOSE_LOSS_EXIT_COMPONENT,
            func=ema_close_loss_exit,
            description=(
                "Trend exit when base close violates aligned EMA for N consecutive base bars."
            ),
        ),
        EMA_CROSS_LOSS_EXIT_COMPONENT: ComponentDefinition(
            role="exits",
            component_id=EMA_CROSS_LOSS_EXIT_COMPONENT,
            func=ema_cross_loss_exit,
            description=(
                "Trend exit on fast/slow EMA cross or adverse EMA order held N base bars."
            ),
        ),
        ATR_STOP_LOSS_COMPONENT: ComponentDefinition(
            role="exits",
            component_id=ATR_STOP_LOSS_COMPONENT,
            func=atr_distance_exit,
            description="ATR distance stop-loss exit.",
        ),
        ATR_TAKE_PROFIT_COMPONENT: ComponentDefinition(
            role="exits",
            component_id=ATR_TAKE_PROFIT_COMPONENT,
            func=atr_distance_exit,
            description="ATR distance take-profit exit.",
        ),
        CONSTANT_USD_STOP_LOSS_COMPONENT: ComponentDefinition(
            role="exits",
            component_id=CONSTANT_USD_STOP_LOSS_COMPONENT,
            func=constant_usd_distance_exit,
            description="Stop loss at a constant USD distance from price (USDT-style markets).",
        ),
        CONSTANT_USD_TAKE_PROFIT_COMPONENT: ComponentDefinition(
            role="exits",
            component_id=CONSTANT_USD_TAKE_PROFIT_COMPONENT,
            func=constant_usd_distance_exit,
            description="Take profit at a constant USD distance from price (USDT-style markets).",
        ),
    },
    "risk": {
        NO_RISK_FILTER_COMPONENT: ComponentDefinition(
            role="risk",
            component_id=NO_RISK_FILTER_COMPONENT,
            func=no_risk_filter,
            description="No risk gate filter (all True).",
        ),
    },
}


def resolve_component(role: str, component_id: str) -> ComponentDefinition:
    """Resolve component definition by role and component id."""

    role_registry = COMPONENT_REGISTRY.get(role)
    if role_registry is None:
        known_roles = ", ".join(sorted(COMPONENT_REGISTRY.keys()))
        raise ValueError(f"unknown component role {role!r}; known roles: {known_roles}")

    component = role_registry.get(component_id)
    if component is None:
        known_ids = ", ".join(sorted(role_registry.keys()))
        raise ValueError(
            f"unknown component_id {component_id!r} for role {role!r}; "
            f"known ids: {known_ids}"
        )
    return component


__all__ = [
    "COMPONENT_REGISTRY",
    "ATR_STOP_LOSS_COMPONENT",
    "ATR_TAKE_PROFIT_COMPONENT",
    "CONSTANT_USD_STOP_LOSS_COMPONENT",
    "CONSTANT_USD_TAKE_PROFIT_COMPONENT",
    "ComponentDefinition",
    "COUNTER_CANDLE_BLOCKER_COMPONENT",
    "EMA_ANCHOR_STACK_TREND_COMPONENT",
    "ANCHOR_STACK_WIDTH_SETUP_COMPONENT",
    "EMA_BOUNCE_COUNTER_SETUP_COMPONENT",
    "NO_BLOCKERS_COMPONENT",
    "NO_SIGNAL_EXIT_COMPONENT",
    "NO_RISK_FILTER_COMPONENT",
    "UNTOUCHED_ANCHOR_SETUP_COMPONENT",
    "RECLAIM_ANCHOR_COMPONENT",
    "STRONG_RECLAIM_ANCHOR_COMPONENT",
    "REQUIRED_COMPONENT_ROLES",
    "RSI_LOOKBACK_EXTREME_BLOCKER_COMPONENT",
    "TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT",
    "RSI_SIGNAL_EXIT_COMPONENT",
    "EMA_CLOSE_LOSS_EXIT_COMPONENT",
    "EMA_CROSS_LOSS_EXIT_COMPONENT",
    "TOUCH_ANCHOR_COMPONENT",
    "HTF_CONTEXT_COMPONENT",
    "no_risk_filter",
    "resolve_component",
]
