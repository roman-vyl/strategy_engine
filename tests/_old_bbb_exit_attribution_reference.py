"""Verbatim old-BBB attribution algorithm -- I2 corrective pass
(`compact-strategy-evaluation-boundary-v1`).

Provenance
----------
Repository: `roman-vyl/_bbb_new_gen`
Commit:     `cddc83663911f646c9bcf2ecfb37b3bed6f4b1d4` (2026-07-05)
Path:       `research/strategies/ema_pullback/execution/exit_attribution.py`

`_finite`, `ExitAttributionContext`, `_agg_sl_tp_at_entry`, and
`_pick_distance_instance` below are copied character-for-character from
that file at that commit (obtained via `git show
cddc8366:research/strategies/ema_pullback/execution/exit_attribution.py`
against the real, remote-tracked `_bbb_new_gen` checkout) -- no logic
was altered, reworded, or "restated from memory." The only change from
the source file is *removal*, not modification: the module-level
`EmaPullbackStrategySpec` import and the one function that used it
(`build_exit_instance_component_map`) are omitted here because neither
is invoked by the two functions this reference exercises, and pulling
in old BBB's full `spec.py`/`data_engine` import chain to satisfy an
unused import would add fragile cross-repo dependencies to this test
suite for no evidentiary benefit.

`_first_fired_signal_instance` is new in this file, but its body is a
verbatim copy of the inner loop from old BBB's own
`classify_exit_attribution` (same file, the trailing `for i, series in
enumerate(masks): ...` block) -- the *only* change is wrapping that
existing inline loop in a standalone function so it can be called
directly against a synthetic per-rule fixture, instead of only being
reachable from inside a full vectorbt trade-record row. The selection
rule itself (group filter `{"always_on", profile}`, first rule index
with `series.iloc[bar_index]` true wins) is unmodified.

This module exists so the I2 corrective-pass proof
(`test_i2_old_bbb_semantics_parity.py`) computes its expected values
from the ACTUAL old-BBB algorithm, not from a re-derivation written by
this migration's own author -- closing the gap the corrective pass was
requested to close (`current Engine` and `test-local reference helpers`
could, in principle, have been consistently wrong together; this module
is not derived from either).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

# --- verbatim from exit_attribution.py -------------------------------------


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


def _finite(x: Any) -> bool:
    if x is None:
        return False
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


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


# --- extracted verbatim from classify_exit_attribution's signal loop -------


def _first_fired_signal_instance(
    ctx: ExitAttributionContext,
    *,
    direction: Literal["long", "short"],
    bar_index: int,
    profile: str,
) -> str | None:
    """Verbatim body of `classify_exit_attribution`'s trailing signal loop
    (same file, lines ~344-357), wrapped in a standalone function so it can
    be exercised directly. Unmodified: group filter `{"always_on",
    profile}`, first rule index (declared order) whose series is true at
    the given bar wins."""

    masks = ctx.long_signal_by_rule if direction == "long" else ctx.short_signal_by_rule
    for i, series in enumerate(masks):
        if series is None:
            continue
        group = ctx.rule_groups[i] if i < len(ctx.rule_groups) else "always_on"
        if group not in {"always_on", profile}:
            continue
        if bool(series.iloc[bar_index]):
            return ctx.instance_ids[i]
    return None
