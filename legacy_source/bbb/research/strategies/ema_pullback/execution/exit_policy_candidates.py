"""Collect bar-open exit_policy candidates for execution-layer close selection."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from research.strategies.ema_pullback.execution.exit_attribution import (
    ExitAttributionContext,
    _agg_sl_tp_at_entry,
    _attribution_for_instance,
    _levels_from_ratios,
    _pick_distance_instance,
    _stop_hit_long,
    _stop_hit_short,
    fill_price_for_distance_exit,
)
from research.strategies.ema_pullback.execution.exits import PROFILE_ORDER, PortfolioExitOutputs
from research.strategies.ema_pullback.execution.managed_components.take import (
    ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP,
)
from research.strategies.ema_pullback.execution.trade_runtime import ExitCandidate


def collect_exit_policy_bar_candidates(
    *,
    bar_idx: int,
    direction: Literal["long", "short"],
    entry_idx: int,
    entry_price: float,
    locked_profile: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    exit_outputs: PortfolioExitOutputs,
    inherited_take_profile: str,
    component_map: dict[str, str] | None,
) -> list[ExitCandidate]:
    ctx = exit_outputs.attribution
    if ctx is None:
        return []

    sl_agg, tp_agg = _agg_sl_tp_at_entry(ctx, entry_idx, profile=locked_profile)
    sl_level, tp_level = _levels_from_ratios(direction, entry_price, sl_agg, tp_agg)

    out: list[ExitCandidate] = []

    if direction == "long":
        if sl_level is not None and sl_agg is not None and _stop_hit_long(
            open_, high, low, sl_level, is_loss=True
        ):
            inst = _pick_distance_instance(
                ctx, entry_idx, exit_kind="stop_loss", agg_value=sl_agg, profile=locked_profile
            )
            if inst:
                price = fill_price_for_distance_exit(
                    "long",
                    open_=open_,
                    high=high,
                    low=low,
                    level=sl_level,
                    is_loss=True,
                )
                out.append(
                    ExitCandidate(
                        layer="exit_policy",
                        rule_id=inst,
                        component_id=(component_map or {}).get(inst),
                        price=price,
                        bar=bar_idx,
                        reason=f"stop_loss:{inst}",
                        candidate_type="stop_loss",
                    )
                )
        if (
            inherited_take_profile != ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP
            and tp_level is not None
            and tp_agg is not None
            and _stop_hit_long(open_, high, low, tp_level, is_loss=False)
        ):
            inst = _pick_distance_instance(
                ctx, entry_idx, exit_kind="take_profit", agg_value=tp_agg, profile=locked_profile
            )
            if inst:
                price = fill_price_for_distance_exit(
                    "long",
                    open_=open_,
                    high=high,
                    low=low,
                    level=tp_level,
                    is_loss=False,
                )
                out.append(
                    ExitCandidate(
                        layer="exit_policy",
                        rule_id=inst,
                        component_id=(component_map or {}).get(inst),
                        price=price,
                        bar=bar_idx,
                        reason=f"take_profit:{inst}",
                        candidate_type="take_profit",
                    )
                )
        prof = locked_profile
        long_exit_series = exit_outputs.long_exits_by_profile.get(prof)
        if long_exit_series is not None and bool(long_exit_series.iloc[bar_idx]):
            out.extend(
                _signal_candidates_for_bar(
                    ctx,
                    bar_idx=bar_idx,
                    direction="long",
                    locked_profile=prof,
                    close=close,
                    component_map=component_map,
                )
            )
    else:
        if sl_level is not None and sl_agg is not None and _stop_hit_short(
            open_, high, low, sl_level, is_loss=True
        ):
            inst = _pick_distance_instance(
                ctx, entry_idx, exit_kind="stop_loss", agg_value=sl_agg, profile=locked_profile
            )
            if inst:
                price = fill_price_for_distance_exit(
                    "short",
                    open_=open_,
                    high=high,
                    low=low,
                    level=sl_level,
                    is_loss=True,
                )
                out.append(
                    ExitCandidate(
                        layer="exit_policy",
                        rule_id=inst,
                        component_id=(component_map or {}).get(inst),
                        price=price,
                        bar=bar_idx,
                        reason=f"stop_loss:{inst}",
                        candidate_type="stop_loss",
                    )
                )
        if (
            inherited_take_profile != ACTIVE_TAKE_PROFILE_DISABLE_INITIAL_TP
            and tp_level is not None
            and tp_agg is not None
            and _stop_hit_short(open_, high, low, tp_level, is_loss=False)
        ):
            inst = _pick_distance_instance(
                ctx, entry_idx, exit_kind="take_profit", agg_value=tp_agg, profile=locked_profile
            )
            if inst:
                price = fill_price_for_distance_exit(
                    "short",
                    open_=open_,
                    high=high,
                    low=low,
                    level=tp_level,
                    is_loss=False,
                )
                out.append(
                    ExitCandidate(
                        layer="exit_policy",
                        rule_id=inst,
                        component_id=(component_map or {}).get(inst),
                        price=price,
                        bar=bar_idx,
                        reason=f"take_profit:{inst}",
                        candidate_type="take_profit",
                    )
                )
        prof = locked_profile
        short_exit_series = exit_outputs.short_exits_by_profile.get(prof)
        if short_exit_series is not None and bool(short_exit_series.iloc[bar_idx]):
            out.extend(
                _signal_candidates_for_bar(
                    ctx,
                    bar_idx=bar_idx,
                    direction="short",
                    locked_profile=prof,
                    close=close,
                    component_map=component_map,
                )
            )

    return out


def _signal_candidates_for_bar(
    ctx: ExitAttributionContext,
    *,
    bar_idx: int,
    direction: Literal["long", "short"],
    locked_profile: str,
    close: float,
    component_map: dict[str, str] | None,
) -> list[ExitCandidate]:
    masks = ctx.long_signal_by_rule if direction == "long" else ctx.short_signal_by_rule
    out: list[ExitCandidate] = []
    for i, series in enumerate(masks):
        if series is None:
            continue
        group = ctx.rule_groups[i] if i < len(ctx.rule_groups) else "always_on"
        if group not in {"always_on", locked_profile}:
            continue
        if not bool(series.iloc[bar_idx]):
            continue
        inst = ctx.instance_ids[i]
        attr = _attribution_for_instance(ctx, inst, prefix="signal", component_map=component_map)
        out.append(
            ExitCandidate(
                layer="exit_policy",
                rule_id=attr.exit_instance_id,
                component_id=attr.exit_component_id,
                price=close,
                bar=bar_idx,
                reason=attr.exit_reason,
                candidate_type="signal",
            )
        )
    return out


def profile_at_bar(
    exit_outputs: PortfolioExitOutputs,
    bar_idx: int,
    side: Literal["long", "short"],
) -> str:
    series = exit_outputs.profile_long if side == "long" else exit_outputs.profile_short
    profile = str(series.iloc[bar_idx])
    return profile if profile in PROFILE_ORDER else "neutral"
