"""Exit reason attribution for vectorbt trades (Step 16)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from research.strategies.ema_pullback.spec import EmaPullbackStrategySpec


@dataclass(frozen=True)
class ExitAttributionContext:
    """Per-rule series aligned with compiled exit policy rule order."""

    index: pd.Index
    instance_ids: tuple[str, ...]
    exit_kinds: tuple[str, ...]
    long_signal_by_rule: tuple[pd.Series | None, ...]
    short_signal_by_rule: tuple[pd.Series | None, ...]
    distance_ratio_by_rule: tuple[pd.Series | None, ...]
    rule_groups: tuple[str, ...] = ()
    context_state: pd.Series | None = None
    sl_stop_agg_by_profile: dict[str, pd.Series] | None = None
    tp_stop_agg_by_profile: dict[str, pd.Series] | None = None
    sl_stop_agg: pd.Series | None = None
    tp_stop_agg: pd.Series | None = None


@dataclass(frozen=True)
class ExitAttributionResult:
    exit_reason: str
    exit_group: str | None
    exit_profile: str | None
    exit_component_id: str | None
    exit_instance_id: str | None
    exit_kind: str | None


def build_exit_instance_component_map(spec: EmaPullbackStrategySpec) -> dict[str, str]:
    """Map exit rule ``instance_id`` → ``component_id`` from compiled exit policy."""

    policy = spec.trade_management.exit_policy
    out: dict[str, str] = {}
    for rule in (
        policy.always_on.exits
        + policy.profiles.aligned.exits
        + policy.profiles.countertrend.exits
        + policy.profiles.neutral.exits
    ):
        out[rule.instance_id] = rule.component_id
    return out


def _finite(x: Any) -> bool:
    if x is None:
        return False
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def _resolve_profile(direction: str, context_state: str) -> str:
    if direction == "long":
        if context_state == "up":
            return "aligned"
        if context_state == "down":
            return "countertrend"
        return "neutral"
    if context_state == "down":
        return "aligned"
    if context_state == "up":
        return "countertrend"
    return "neutral"


def _null_attribution(exit_reason: str) -> ExitAttributionResult:
    return ExitAttributionResult(exit_reason, None, None, None, None, None)


def _rule_index_for_instance(ctx: ExitAttributionContext, instance_id: str) -> int | None:
    for i, inst in enumerate(ctx.instance_ids):
        if inst == instance_id:
            return i
    return None


def _metadata_for_rule(
    ctx: ExitAttributionContext,
    rule_i: int,
    *,
    component_map: dict[str, str] | None,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    inst = ctx.instance_ids[rule_i]
    kind = ctx.exit_kinds[rule_i]
    group = ctx.rule_groups[rule_i] if rule_i < len(ctx.rule_groups) else "always_on"
    component_id = (component_map or {}).get(inst)
    if group == "always_on":
        return "always_on", None, component_id, inst, kind
    if group in {"aligned", "countertrend", "neutral"}:
        return "profile", group, component_id, inst, kind
    return None, None, component_id, inst, kind


def _attribution_for_instance(
    ctx: ExitAttributionContext,
    instance_id: str,
    *,
    prefix: str,
    component_map: dict[str, str] | None,
) -> ExitAttributionResult:
    rule_i = _rule_index_for_instance(ctx, instance_id)
    if rule_i is None:
        return _null_attribution("unknown")
    exit_group, exit_profile, exit_component_id, exit_instance_id, exit_kind = _metadata_for_rule(
        ctx, rule_i, component_map=component_map
    )
    return ExitAttributionResult(
        f"{prefix}:{instance_id}",
        exit_group,
        exit_profile,
        exit_component_id,
        exit_instance_id,
        exit_kind,
    )


def _agg_sl_tp_at_entry(
    ctx: ExitAttributionContext,
    entry_idx: int,
    *,
    profile: str,
) -> tuple[float | None, float | None]:
    if ctx.sl_stop_agg_by_profile is not None and ctx.tp_stop_agg_by_profile is not None:
        sl_a = ctx.sl_stop_agg_by_profile.get(profile)
        tp_a = ctx.tp_stop_agg_by_profile.get(profile)
        if sl_a is None or tp_a is None:
            return None, None
        sl_a = sl_a.iloc[entry_idx]
        tp_a = tp_a.iloc[entry_idx]
    else:
        if ctx.sl_stop_agg is None or ctx.tp_stop_agg is None:
            return None, None
        sl_a = ctx.sl_stop_agg.iloc[entry_idx]
        tp_a = ctx.tp_stop_agg.iloc[entry_idx]
    sl_v = float(sl_a) if _finite(sl_a) else None
    tp_v = float(tp_a) if _finite(tp_a) else None
    return sl_v, tp_v


def _pick_distance_instance(
    ctx: ExitAttributionContext,
    entry_idx: int,
    *,
    exit_kind: Literal["stop_loss", "take_profit"],
    agg_value: float,
    profile: str,
) -> str | None:
    """Which distance rule produced the aggregate min at ``entry_idx`` (first in spec on tie)."""

    eps = 1e-9 * max(1.0, abs(agg_value))
    best: tuple[int, str] | None = None
    for i, kind in enumerate(ctx.exit_kinds):
        if kind != exit_kind:
            continue
        group = ctx.rule_groups[i] if i < len(ctx.rule_groups) else "always_on"
        if group not in {"always_on", profile}:
            continue
        series = ctx.distance_ratio_by_rule[i]
        if series is None:
            continue
        v = series.iloc[entry_idx]
        if not _finite(v):
            continue
        fv = float(v)
        if abs(fv - agg_value) <= eps:
            cand = (i, ctx.instance_ids[i])
            if best is None or i < best[0]:
                best = cand
    return None if best is None else best[1]


def _stop_hit_long(
    o: float,
    h: float,
    l: float,
    level: float,
    *,
    is_loss: bool,
) -> bool:
    """Mirror vectorbt ``get_stop_price_nb`` hit semantics (long: SL below, TP above)."""

    if is_loss:
        stop_price = level
        if o <= stop_price:
            return True
        return l <= stop_price <= h
    stop_price = level
    if stop_price <= o:
        return True
    return l <= stop_price <= h


def _stop_hit_short(
    o: float,
    h: float,
    l: float,
    level: float,
    *,
    is_loss: bool,
) -> bool:
    """Short: SL above anchor; TP below."""

    if is_loss:
        stop_price = level
        if stop_price <= o:
            return True
        return l <= stop_price <= h
    stop_price = level
    if o <= stop_price:
        return True
    return l <= stop_price <= h


def fill_price_for_distance_exit(
    direction: Literal["long", "short"],
    *,
    open_: float,
    high: float,
    low: float,
    level: float,
    is_loss: bool,
) -> float:
    """Fill price when a distance stop/TP level is hit (mirrors ``get_stop_price_nb``)."""

    if direction == "long":
        if is_loss:
            if open_ <= level:
                return open_
            if low <= level <= high:
                return level
        else:
            if level <= open_:
                return open_
            if low <= level <= high:
                return level
    else:
        if is_loss:
            if level <= open_:
                return open_
            if low <= level <= high:
                return level
        else:
            if open_ <= level:
                return open_
            if low <= level <= high:
                return level
    return level


def _levels_from_ratios(
    direction: str,
    stop_anchor: float,
    sl_r: float | None,
    tp_r: float | None,
) -> tuple[float | None, float | None]:
    """Absolute SL/TP levels from vectorbt default ``stop_entry_price`` = close (long/short formulas)."""

    if direction == "long":
        sl_level = stop_anchor * (1.0 - sl_r) if sl_r is not None else None
        tp_level = stop_anchor * (1.0 + tp_r) if tp_r is not None else None
        return sl_level, tp_level
    sl_level = stop_anchor * (1.0 + sl_r) if sl_r is not None else None
    tp_level = stop_anchor * (1.0 - tp_r) if tp_r is not None else None
    return sl_level, tp_level


def classify_exit_attribution(
    *,
    row: dict[str, Any],
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series,
    ctx: ExitAttributionContext,
    component_map: dict[str, str] | None = None,
) -> ExitAttributionResult:
    """Return ``exit_reason`` and structured exit metadata for one trade record row."""

    status_code = int(row.get("status", 0))
    if status_code == 0:
        return _null_attribution("open")

    direction_code = int(row.get("direction", 0))
    direction = "long" if direction_code == 0 else "short"

    exit_idx_raw = row.get("exit_idx")
    entry_idx_raw = row.get("entry_idx")
    if exit_idx_raw is None or entry_idx_raw is None:
        return _null_attribution("unknown")
    try:
        exit_idx = int(exit_idx_raw)
        entry_idx = int(entry_idx_raw)
    except (TypeError, ValueError):
        return _null_attribution("unknown")

    if exit_idx < 0 or entry_idx < 0 or exit_idx >= len(close) or entry_idx >= len(close):
        return _null_attribution("unknown")

    stop_anchor = float(close.iloc[entry_idx])
    if not math.isfinite(stop_anchor):
        return _null_attribution("unknown")

    o_x = float(open_.iloc[exit_idx])
    h_x = float(high.iloc[exit_idx])
    l_x = float(low.iloc[exit_idx])
    if not all(map(math.isfinite, (o_x, h_x, l_x))):
        return _null_attribution("unknown")

    raw_state = ctx.context_state.iloc[entry_idx] if ctx.context_state is not None else "neutral"
    state = str(raw_state) if isinstance(raw_state, str) else "neutral"
    profile = _resolve_profile(direction, state)
    sl_agg, tp_agg = _agg_sl_tp_at_entry(ctx, entry_idx, profile=profile)
    sl_level, tp_level = _levels_from_ratios(direction, stop_anchor, sl_agg, tp_agg)

    if direction == "long":
        if sl_level is not None and sl_agg is not None and _stop_hit_long(
            o_x, h_x, l_x, sl_level, is_loss=True
        ):
            inst = _pick_distance_instance(
                ctx, entry_idx, exit_kind="stop_loss", agg_value=sl_agg, profile=profile
            )
            if inst:
                return _attribution_for_instance(
                    ctx, inst, prefix="stop_loss", component_map=component_map
                )
            return _null_attribution("unknown")
        if tp_level is not None and tp_agg is not None and _stop_hit_long(
            o_x, h_x, l_x, tp_level, is_loss=False
        ):
            inst = _pick_distance_instance(
                ctx, entry_idx, exit_kind="take_profit", agg_value=tp_agg, profile=profile
            )
            if inst:
                return _attribution_for_instance(
                    ctx, inst, prefix="take_profit", component_map=component_map
                )
            return _null_attribution("unknown")
    else:
        if sl_level is not None and sl_agg is not None and _stop_hit_short(
            o_x, h_x, l_x, sl_level, is_loss=True
        ):
            inst = _pick_distance_instance(
                ctx, entry_idx, exit_kind="stop_loss", agg_value=sl_agg, profile=profile
            )
            if inst:
                return _attribution_for_instance(
                    ctx, inst, prefix="stop_loss", component_map=component_map
                )
            return _null_attribution("unknown")
        if tp_level is not None and tp_agg is not None and _stop_hit_short(
            o_x, h_x, l_x, tp_level, is_loss=False
        ):
            inst = _pick_distance_instance(
                ctx, entry_idx, exit_kind="take_profit", agg_value=tp_agg, profile=profile
            )
            if inst:
                return _attribution_for_instance(
                    ctx, inst, prefix="take_profit", component_map=component_map
                )
            return _null_attribution("unknown")

    masks = ctx.long_signal_by_rule if direction == "long" else ctx.short_signal_by_rule
    for i, series in enumerate(masks):
        if series is None:
            continue
        group = ctx.rule_groups[i] if i < len(ctx.rule_groups) else "always_on"
        if group not in {"always_on", profile}:
            continue
        if bool(series.iloc[exit_idx]):
            inst = ctx.instance_ids[i]
            exit_group, exit_profile, exit_component_id, exit_instance_id, exit_kind = _metadata_for_rule(
                ctx, i, component_map=component_map
            )
            return ExitAttributionResult(
                f"signal:{inst}",
                exit_group,
                exit_profile,
                exit_component_id,
                exit_instance_id,
                exit_kind,
            )

    return _null_attribution("unknown")


def classify_exit_reason(
    *,
    row: dict[str, Any],
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series,
    ctx: ExitAttributionContext,
) -> str:
    """Return ``exit_reason`` string for one ``pf.trades.records`` row."""

    return classify_exit_attribution(
        row=row,
        close=close,
        high=high,
        low=low,
        open_=open_,
        ctx=ctx,
    ).exit_reason
