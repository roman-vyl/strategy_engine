"""Exit policy compiler for vectorbt-facing outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from research.strategies.ema_pullback.components.registry import resolve_component
from research.strategies.ema_pullback.context.bundle import ContextBundle
from research.strategies.ema_pullback.context.pipeline import require_context_bundle
from research.strategies.ema_pullback.context.evaluation import (
    SideAwareEvaluationContext,
    evaluate_context_consumption,
)
from research.strategies.ema_pullback.context.policies import EXIT_PROFILE_BY_HTF_STATE_POLICY
from research.strategies.ema_pullback.execution.exit_attribution import ExitAttributionContext
from research.strategies.ema_pullback.features.plan import FeaturePlan
from research.strategies.ema_pullback.spec import (
    EmaPullbackStrategySpec,
    EmaSpec,
    ExitRuleSpec,
    RsiFeatureSpec,
    TradeSide,
)

PROFILE_ORDER = ("aligned", "countertrend", "neutral")
STATE_ORDER = ("up", "down", "neutral")


@dataclass(frozen=True)
class PortfolioExitOutputs:
    exits: pd.Series
    short_exits: pd.Series
    sl_stop: pd.Series
    tp_stop: pd.Series
    stop_ready_long: pd.Series
    stop_ready_short: pd.Series
    context_state: pd.Series
    profile_long: pd.Series
    profile_short: pd.Series
    long_exits_by_profile: dict[str, pd.Series] = field(default_factory=dict)
    short_exits_by_profile: dict[str, pd.Series] = field(default_factory=dict)
    sl_stop_by_profile: dict[str, pd.Series] = field(default_factory=dict)
    tp_stop_by_profile: dict[str, pd.Series] = field(default_factory=dict)
    output_counters: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    attribution: ExitAttributionContext | None = None

    def stop_kwargs(self) -> dict[str, pd.Series]:
        return {
            "sl_stop": self.sl_stop,
            "tp_stop": self.tp_stop,
        }


def compose_exit_signals(signals: tuple[pd.Series, ...], *, index: pd.Index) -> pd.Series:
    """Any signal exit rule can close a trade."""

    if not signals:
        return pd.Series(False, index=index, dtype=bool)
    out = signals[0].fillna(False).astype(bool)
    for signal in signals[1:]:
        out = out | signal.fillna(False).astype(bool)
    return out.astype(bool)


def _false_series(index: pd.Index) -> pd.Series:
    return pd.Series(False, index=index, dtype=bool)


def _nan_series(index: pd.Index) -> pd.Series:
    return pd.Series(float("nan"), index=index, dtype=float)


def _rsi_column(plan: FeaturePlan, rsi: RsiFeatureSpec | None) -> str | None:
    if rsi is None:
        return None
    return plan.rsi_columns[(rsi.timeframe, rsi.period)]


def _distance_column(plan: FeaturePlan, rule: ExitRuleSpec) -> str | None:
    if rule.distance is None:
        return None
    return plan.exit_distance_columns[rule.instance_id]


def _ema_column(plan: FeaturePlan, ema: EmaSpec | None) -> str | None:
    if ema is None:
        return None
    return plan.ema_column(ema)


def _signal_series_for_side(
    df: pd.DataFrame,
    *,
    side: TradeSide,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    anchor_col: str,
    exit_fn: Callable[..., pd.Series],
    rule: ExitRuleSpec,
) -> pd.Series:
    if not spec.trade_sides.includes(side):
        return _false_series(df.index)
    ema_col = _ema_column(plan, rule.ema)
    fast_col = _ema_column(plan, rule.fast_ema)
    slow_col = _ema_column(plan, rule.slow_ema)
    s = exit_fn(
        df,
        anchor_col=anchor_col,
        side=side,
        rule=rule,
        rsi_col=_rsi_column(plan, rule.rsi),
        ema_col=ema_col,
        fast_col=fast_col,
        slow_col=slow_col,
    )
    return s.fillna(False).astype(bool)


def _compile_signal_series(
    *,
    spec: EmaPullbackStrategySpec,
    by_instance_long: dict[str, pd.Series],
    by_instance_short: dict[str, pd.Series],
    index: pd.Index,
) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    always_on = spec.trade_management.exit_policy.always_on.exits
    profiles = spec.trade_management.exit_policy.profiles
    profile_rules = {
        "aligned": profiles.aligned.exits,
        "countertrend": profiles.countertrend.exits,
        "neutral": profiles.neutral.exits,
    }
    out_long: dict[str, pd.Series] = {}
    out_short: dict[str, pd.Series] = {}
    always_on_long = [by_instance_long[r.instance_id] for r in always_on if r.exit_kind == "signal"]
    always_on_short = [by_instance_short[r.instance_id] for r in always_on if r.exit_kind == "signal"]
    for profile in PROFILE_ORDER:
        local_long = always_on_long + [
            by_instance_long[r.instance_id] for r in profile_rules[profile] if r.exit_kind == "signal"
        ]
        local_short = always_on_short + [
            by_instance_short[r.instance_id] for r in profile_rules[profile] if r.exit_kind == "signal"
        ]
        out_long[profile] = compose_exit_signals(tuple(local_long), index=index)
        out_short[profile] = compose_exit_signals(tuple(local_short), index=index)
    return out_long, out_short


def _compile_distance_series(
    *,
    spec: EmaPullbackStrategySpec,
    close: pd.Series,
    by_instance_distance_ratio: dict[str, pd.Series],
    kind: str,
) -> dict[str, pd.Series]:
    always_on = spec.trade_management.exit_policy.always_on.exits
    profiles = spec.trade_management.exit_policy.profiles
    profile_rules = {
        "aligned": profiles.aligned.exits,
        "countertrend": profiles.countertrend.exits,
        "neutral": profiles.neutral.exits,
    }
    out: dict[str, pd.Series] = {}
    always_on_parts = [
        by_instance_distance_ratio[r.instance_id]
        for r in always_on
        if r.exit_kind == kind and r.instance_id in by_instance_distance_ratio
    ]
    for profile in PROFILE_ORDER:
        local = always_on_parts + [
            by_instance_distance_ratio[r.instance_id]
            for r in profile_rules[profile]
            if r.exit_kind == kind and r.instance_id in by_instance_distance_ratio
        ]
        if local:
            out[profile] = pd.concat(local, axis=1).min(axis=1).astype(float)
        else:
            out[profile] = _nan_series(close.index)
    return out


def _selected_series_by_profile(
    *,
    profile_series: pd.Series,
    values_by_profile: dict[str, pd.Series],
    default: pd.Series,
) -> pd.Series:
    out = default.copy()
    for profile in PROFILE_ORDER:
        mask = profile_series.eq(profile)
        if mask.any():
            out.loc[mask] = values_by_profile[profile].loc[mask]
    return out


def _stop_ready(sl: pd.Series, tp: pd.Series) -> pd.Series:
    """Readiness for one exit-policy group (always_on or a single profile).

    Uses global ``.any()`` only within this group's series. NaN SL on a bar means
    this group has no SL rule for that bar, not a missing warmup value.
    """
    ready = pd.Series(True, index=sl.index, dtype=bool)
    if sl.notna().any():
        ready = ready & sl.notna()
    if tp.notna().any():
        ready = ready & tp.notna()
    return ready


def _stop_ready_by_profile(
    sl_by_profile: dict[str, pd.Series],
    tp_by_profile: dict[str, pd.Series],
) -> dict[str, pd.Series]:
    return {
        profile: _stop_ready(sl_by_profile[profile], tp_by_profile[profile])
        for profile in PROFILE_ORDER
    }


def build_exit_outputs_from_spec(
    df: pd.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    *,
    context_bundle: ContextBundle | None = None,
) -> PortfolioExitOutputs:
    """Build profile-aware signal exits and stop/take series."""

    require_context_bundle(spec, context_bundle)
    all_exit_rules = (
        spec.trade_management.exit_policy.always_on.exits
        + spec.trade_management.exit_policy.profiles.aligned.exits
        + spec.trade_management.exit_policy.profiles.countertrend.exits
        + spec.trade_management.exit_policy.profiles.neutral.exits
    )
    resolved_rules = tuple(
        (resolve_component("exits", rule.component_id).func, rule) for rule in all_exit_rules
    )
    anchor_col = plan.anchor_columns["anchor"]
    index = df.index
    close = df["close"].astype(float)
    nan_series = pd.Series(float("nan"), index=index, dtype=float)

    n_rules = len(resolved_rules)
    long_by_idx: list[pd.Series | None] = [None] * n_rules
    short_by_idx: list[pd.Series | None] = [None] * n_rules
    dist_ratio_by_idx: list[pd.Series | None] = [None] * n_rules
    rule_groups: list[str] = []
    instance_ids: list[str] = []
    exit_kinds: list[str] = []
    long_by_instance: dict[str, pd.Series] = {}
    short_by_instance: dict[str, pd.Series] = {}
    distance_ratio_by_instance: dict[str, pd.Series] = {}
    counters: list[dict[str, Any]] = []

    always_on_ids = {rule.instance_id for rule in spec.trade_management.exit_policy.always_on.exits}
    aligned_ids = {rule.instance_id for rule in spec.trade_management.exit_policy.profiles.aligned.exits}
    countertrend_ids = {rule.instance_id for rule in spec.trade_management.exit_policy.profiles.countertrend.exits}
    neutral_ids = {rule.instance_id for rule in spec.trade_management.exit_policy.profiles.neutral.exits}

    def _rule_group(rule: ExitRuleSpec) -> str:
        if rule.instance_id in always_on_ids:
            return "always_on"
        if rule.instance_id in aligned_ids:
            return "aligned"
        if rule.instance_id in countertrend_ids:
            return "countertrend"
        if rule.instance_id in neutral_ids:
            return "neutral"
        return "neutral"

    for exit_fn, rule in resolved_rules:
        instance_ids.append(rule.instance_id)
        exit_kinds.append(rule.exit_kind)
        rule_groups.append(_rule_group(rule))

        if rule.exit_kind == "signal":
            long_s = _signal_series_for_side(
                df, side="long", spec=spec, plan=plan, anchor_col=anchor_col, exit_fn=exit_fn, rule=rule
            )
            short_s = _signal_series_for_side(
                df, side="short", spec=spec, plan=plan, anchor_col=anchor_col, exit_fn=exit_fn, rule=rule
            )
            rule_i = len(instance_ids) - 1
            long_by_idx[rule_i] = long_s
            short_by_idx[rule_i] = short_s
            long_by_instance[rule.instance_id] = long_s
            short_by_instance[rule.instance_id] = short_s
            if spec.trade_sides.includes("long"):
                counters.append(
                    {
                        "role": "exits",
                        "component_id": rule.component_id,
                        "instance_id": rule.instance_id,
                        "exit_kind": rule.exit_kind,
                        "side": "long",
                        "output_type": "boolean",
                        "counters": {"signal_count": int(long_s.sum())},
                    }
                )
            if spec.trade_sides.includes("short"):
                counters.append(
                    {
                        "role": "exits",
                        "component_id": rule.component_id,
                        "instance_id": rule.instance_id,
                        "exit_kind": rule.exit_kind,
                        "side": "short",
                        "output_type": "boolean",
                        "counters": {"signal_count": int(short_s.sum())},
                    }
                )
        else:
            distance_col = _distance_column(plan, rule)
            distance = exit_fn(df, rule=rule, distance_col=distance_col).astype(float)
            rule_i = len(instance_ids) - 1
            ratio = distance / close
            dist_ratio_by_idx[rule_i] = ratio
            distance_ratio_by_instance[rule.instance_id] = ratio
            non_null_count = int(distance.notna().sum())
            counters.append(
                {
                    "role": "exits",
                    "component_id": rule.component_id,
                    "instance_id": rule.instance_id,
                    "exit_kind": rule.exit_kind,
                    "side": None,
                    "output_type": "distance",
                    "counters": {
                        "ready_count": non_null_count,
                        "non_null_distance_count": non_null_count,
                    },
                }
            )
    consumption = spec.trade_management.exit_policy.context_consumption
    if consumption is not None:
        if consumption.policy.policy_id != EXIT_PROFILE_BY_HTF_STATE_POLICY:
            raise ValueError(
                "unsupported exit_policy context_consumption.policy_id: "
                f"{consumption.policy.policy_id!r}"
            )
        assert context_bundle is not None
        result = evaluate_context_consumption(
            consumption,
            SideAwareEvaluationContext(
                context_bundle=context_bundle,
                index=index,
                enabled_sides=spec.trade_sides.enabled,
            ),
        )
        context_state = result.raw_state_series
        if context_state is None:
            raise ValueError("exit_profile_by_htf_state result missing raw_state_series")
        profile_long = result.profile_long
        profile_short = result.profile_short
        assert profile_long is not None and profile_short is not None
    else:
        context_state = pd.Series("neutral", index=index, dtype="object")
        profile_long = pd.Series("neutral", index=index, dtype="object")
        profile_short = pd.Series("neutral", index=index, dtype="object")

    long_exits_by_profile, short_exits_by_profile = _compile_signal_series(
        spec=spec,
        by_instance_long=long_by_instance,
        by_instance_short=short_by_instance,
        index=index,
    )
    sl_by_profile = _compile_distance_series(
        spec=spec,
        close=close,
        by_instance_distance_ratio=distance_ratio_by_instance,
        kind="stop_loss",
    )
    tp_by_profile = _compile_distance_series(
        spec=spec,
        close=close,
        by_instance_distance_ratio=distance_ratio_by_instance,
        kind="take_profit",
    )
    long_exits = _selected_series_by_profile(
        profile_series=profile_long,
        values_by_profile=long_exits_by_profile,
        default=_false_series(index),
    ).fillna(False).astype(bool)
    short_exits = _selected_series_by_profile(
        profile_series=profile_short,
        values_by_profile=short_exits_by_profile,
        default=_false_series(index),
    ).fillna(False).astype(bool)
    sl_stop_long = _selected_series_by_profile(
        profile_series=profile_long,
        values_by_profile=sl_by_profile,
        default=nan_series,
    ).astype(float)
    tp_stop_long = _selected_series_by_profile(
        profile_series=profile_long,
        values_by_profile=tp_by_profile,
        default=nan_series,
    ).astype(float)
    sl_stop_short = _selected_series_by_profile(
        profile_series=profile_short,
        values_by_profile=sl_by_profile,
        default=nan_series,
    ).astype(float)
    tp_stop_short = _selected_series_by_profile(
        profile_series=profile_short,
        values_by_profile=tp_by_profile,
        default=nan_series,
    ).astype(float)
    stop_ready_by_profile = _stop_ready_by_profile(sl_by_profile, tp_by_profile)
    stop_ready_long = _selected_series_by_profile(
        profile_series=profile_long,
        values_by_profile=stop_ready_by_profile,
        default=pd.Series(True, index=index, dtype=bool),
    ).fillna(False).astype(bool)
    stop_ready_short = _selected_series_by_profile(
        profile_series=profile_short,
        values_by_profile=stop_ready_by_profile,
        default=pd.Series(True, index=index, dtype=bool),
    ).fillna(False).astype(bool)

    attribution = ExitAttributionContext(
        index=index,
        instance_ids=tuple(instance_ids),
        rule_groups=tuple(rule_groups),
        exit_kinds=tuple(exit_kinds),
        long_signal_by_rule=tuple(long_by_idx),
        short_signal_by_rule=tuple(short_by_idx),
        distance_ratio_by_rule=tuple(dist_ratio_by_idx),
        context_state=context_state,
        sl_stop_agg_by_profile={key: value for key, value in sl_by_profile.items()},
        tp_stop_agg_by_profile={key: value for key, value in tp_by_profile.items()},
        sl_stop_agg=sl_stop_long,
        tp_stop_agg=tp_stop_long,
    )

    return PortfolioExitOutputs(
        exits=long_exits,
        short_exits=short_exits,
        sl_stop=sl_stop_long,
        tp_stop=tp_stop_long,
        stop_ready_long=stop_ready_long,
        stop_ready_short=stop_ready_short,
        context_state=context_state,
        profile_long=profile_long,
        profile_short=profile_short,
        long_exits_by_profile=long_exits_by_profile,
        short_exits_by_profile=short_exits_by_profile,
        sl_stop_by_profile=sl_by_profile,
        tp_stop_by_profile=tp_by_profile,
        output_counters=tuple(counters),
        attribution=attribution,
    )
