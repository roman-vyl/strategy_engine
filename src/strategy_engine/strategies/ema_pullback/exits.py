"""BBB-compatible profile-aware exit policy evaluation."""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from typing import Any, cast

import numpy as np
import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, node_spec
from strategy_engine.domain.values import normalized_decimal_text
from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.indicators.evaluation_context import EvaluationContext, compute_through
from strategy_engine.indicators.market_arrays import frame_market_arrays
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
    resolve_exit_profiles,
)
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    EXIT_DISTANCE_SUPPORTED as _DISTANCE_COMPONENTS,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    EXIT_SIGNAL_SUPPORTED as _SIGNAL_COMPONENTS,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import (
    resolve_exit_rule_groups as _policy_rules,
)

_PROFILE_ORDER = ("aligned", "countertrend", "neutral")
_PROFILE_CODE = {name: index for index, name in enumerate(_PROFILE_ORDER)}


@dataclass(frozen=True, slots=True)
class ExitRuleEvidence:
    instance_id: str
    component_id: str
    exit_kind: str
    group: str
    side: str | None
    signal: tuple[bool, ...] | None = None
    distance_ratio: tuple[float | None, ...] | None = None

    def to_wire(self) -> dict[str, object]:
        return {
            "instance_id": self.instance_id,
            "component_id": self.component_id,
            "exit_kind": self.exit_kind,
            "group": self.group,
            "side": self.side,
            "signal": list(self.signal) if self.signal is not None else None,
            "distance_ratio": (
                [_decimal_or_none(value) for value in self.distance_ratio]
                if self.distance_ratio is not None
                else None
            ),
            "counters": {
                "signal_count": sum(self.signal) if self.signal is not None else None,
                "ready_count": (
                    sum(value is not None for value in self.distance_ratio)
                    if self.distance_ratio is not None
                    else None
                ),
            },
        }


@dataclass(frozen=True, slots=True)
class ExitPolicyEvaluation:
    context_state: tuple[str, ...]
    profile_long: tuple[str, ...]
    profile_short: tuple[str, ...]
    signal_exit_long: tuple[bool, ...]
    signal_exit_short: tuple[bool, ...]
    stop_loss_ratio_long: tuple[float | None, ...]
    stop_loss_ratio_short: tuple[float | None, ...]
    take_profit_ratio_long: tuple[float | None, ...]
    take_profit_ratio_short: tuple[float | None, ...]
    stop_loss_distance_long: tuple[float | None, ...]
    stop_loss_distance_short: tuple[float | None, ...]
    take_profit_distance_long: tuple[float | None, ...]
    take_profit_distance_short: tuple[float | None, ...]
    stop_ready_long: tuple[bool, ...]
    stop_ready_short: tuple[bool, ...]
    signal_by_profile_long: dict[str, tuple[bool, ...]]
    signal_by_profile_short: dict[str, tuple[bool, ...]]
    stop_loss_by_profile: dict[str, tuple[float | None, ...]]
    take_profit_by_profile: dict[str, tuple[float | None, ...]]
    rule_evidence: tuple[ExitRuleEvidence, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "context_state": list(self.context_state),
            "profile_long": list(self.profile_long),
            "profile_short": list(self.profile_short),
            "signal_exit": {
                "long": list(self.signal_exit_long),
                "short": list(self.signal_exit_short),
            },
            "stop_loss_ratio": {
                "long": [_decimal_or_none(value) for value in self.stop_loss_ratio_long],
                "short": [_decimal_or_none(value) for value in self.stop_loss_ratio_short],
            },
            "take_profit_ratio": {
                "long": [_decimal_or_none(value) for value in self.take_profit_ratio_long],
                "short": [_decimal_or_none(value) for value in self.take_profit_ratio_short],
            },
            "stop_ready": {
                "long": list(self.stop_ready_long),
                "short": list(self.stop_ready_short),
            },
            "by_profile": {
                "signal_long": {
                    key: list(value) for key, value in self.signal_by_profile_long.items()
                },
                "signal_short": {
                    key: list(value) for key, value in self.signal_by_profile_short.items()
                },
                "stop_loss_ratio": {
                    key: [_decimal_or_none(item) for item in value]
                    for key, value in self.stop_loss_by_profile.items()
                },
                "take_profit_ratio": {
                    key: [_decimal_or_none(item) for item in value]
                    for key, value in self.take_profit_by_profile.items()
                },
            },
            "rules": [item.to_wire() for item in self.rule_evidence],
        }


def _decimal_or_none(value: float | None) -> str | None:
    if value is None or not isfinite(value):
        return None
    return normalized_decimal_text(Decimal(str(value)))


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _list(value: object, path: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise InvalidRequestError(f"{path} must be a list")
    return tuple(_mapping(item, f"{path}[{index}]") for index, item in enumerate(value))


def _enabled_sides(raw_spec: Mapping[str, Any]) -> tuple[str, ...]:
    raw: object = raw_spec.get("trade_sides", ["long"])
    if isinstance(raw, Mapping):
        raw = raw.get("enabled", ["long"])
    if not isinstance(raw, (list, tuple)):
        raise InvalidRequestError("raw_spec.trade_sides must be a list")
    sides = tuple(str(item) for item in raw)
    if not sides or any(side not in {"long", "short"} for side in sides):
        raise InvalidRequestError("raw_spec.trade_sides must contain long/short")
    return sides


def _frame_dataframe(frame: FeatureFrameLike) -> pd.DataFrame:
    if len(frame.market_bars) != len(frame.time_ms):
        raise InvalidRequestError("market bars unavailable for exit policy")
    arrays = frame_market_arrays(frame)
    data: dict[str, object] = arrays.ohlcv_columns()
    for output_id, values in frame.series.items():
        data[output_id] = [float("nan") if value is None else float(value) for value in values]
    return pd.DataFrame(data, index=arrays.index())


def _ema_column(raw: object, plan: EmaPullbackFeaturePlan, path: str) -> str:
    payload = _mapping(raw, path)
    timeframe = str(payload.get("timeframe", "base"))
    period = int(cast(int | str, payload.get("period")))
    try:
        return plan.ema_columns[(timeframe, period)]
    except KeyError as exc:
        raise InvalidRequestError("missing EMA mapping for exit", path=path) from exc


def _require_confirm_bars(confirm_bars: int) -> None:
    if confirm_bars < 1:
        raise InvalidRequestError("confirm_bars must be >= 1")


def _confirm_bars(rule: Mapping[str, Any]) -> int:
    """Effective `confirm_bars`, post-default (shared by compute and resolve)."""

    return int(rule.get("confirm_bars", 1))


def _rsi_exit_key(rule: Mapping[str, Any]) -> tuple[str, int]:
    """`plan.rsi_columns` key of an RSI signal exit (shared by compute and
    resolve)."""

    rsi = _mapping(rule.get("rsi"), "exit.rsi")
    return str(rsi.get("timeframe", "base")), int(rsi.get("period", 14))


def _rsi_exit_threshold(rule: Mapping[str, Any], side: str) -> float:
    """The one threshold an RSI signal exit reads for `side` (shared by
    compute and resolve)."""

    if side == "long":
        threshold = rule.get("long_exit_above")
        if threshold is None:
            raise InvalidRequestError("rsi_signal_exit requires long_exit_above")
        return float(threshold)
    threshold = rule.get("short_exit_below")
    if threshold is None:
        raise InvalidRequestError("rsi_signal_exit requires short_exit_below")
    return float(threshold)


def _consecutive_true(condition: pd.Series, confirm_bars: int) -> pd.Series:
    _require_confirm_bars(confirm_bars)
    cond = condition.fillna(False).astype(bool)
    if confirm_bars == 1:
        return cond
    return (
        cond.astype(int)
        .rolling(confirm_bars, min_periods=confirm_bars)
        .min()
        .fillna(0)
        .astype(bool)
    )


def _signal_rule(
    df: pd.DataFrame,
    rule: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    side: str,
) -> pd.Series:
    component_id = str(rule.get("component_id", ""))
    if component_id == "no_signal_exit":
        return pd.Series(False, index=df.index, dtype=bool)
    if component_id == "rsi_signal_exit":
        key = _rsi_exit_key(rule)
        try:
            values = df[plan.rsi_columns[key]].astype(float)
        except KeyError as exc:
            raise InvalidRequestError("missing RSI mapping for exit") from exc
        threshold = _rsi_exit_threshold(rule, side)
        if side == "long":
            return (values > threshold).fillna(False).astype(bool)
        return (values < threshold).fillna(False).astype(bool)
    if component_id == "ema_close_loss_exit":
        ema = df[_ema_column(rule.get("ema"), plan, "exit.ema")].astype(float)
        close = df["close"].astype(float)
        condition = close < ema if side == "long" else close > ema
        return _consecutive_true(condition, _confirm_bars(rule))
    if component_id == "ema_cross_loss_exit":
        fast = df[_ema_column(rule.get("fast_ema"), plan, "exit.fast_ema")].astype(float)
        slow = df[_ema_column(rule.get("slow_ema"), plan, "exit.slow_ema")].astype(float)
        confirm_bars = _confirm_bars(rule)
        previous_fast = fast.shift(1)
        previous_slow = slow.shift(1)
        if side == "long":
            cross = (fast < slow) & (previous_fast >= previous_slow)
            adverse = fast < slow
        else:
            cross = (fast > slow) & (previous_fast <= previous_slow)
            adverse = fast > slow
        if confirm_bars == 1:
            return cross.fillna(False).astype(bool)
        adverse_hold = _consecutive_true(adverse, confirm_bars)
        cross_in_window = (
            cross.fillna(False)
            .astype(int)
            .rolling(confirm_bars, min_periods=1)
            .max()
            .fillna(0)
            .astype(bool)
        )
        return (adverse_hold & cross_in_window).astype(bool)
    raise InvalidRequestError("unsupported signal exit component", component_id=component_id)


_ATR_DISTANCE_COMPONENTS = frozenset({"atr_stop_loss", "atr_take_profit"})
_USD_DISTANCE_COMPONENTS = frozenset({"constant_usd_stop_loss", "constant_usd_take_profit"})


def _usd_distance(rule: Mapping[str, Any]) -> float:
    """Effective constant USD distance (shared by compute and resolve)."""

    raw_distance = rule.get("usd_distance")
    if raw_distance is None:
        raise InvalidRequestError("constant USD exit requires usd_distance")
    return float(raw_distance)


def _distance(
    df: pd.DataFrame,
    rule: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
) -> tuple[pd.Series, pd.Series]:
    component_id = str(rule.get("component_id", ""))
    if component_id in _ATR_DISTANCE_COMPONENTS:
        instance_id = str(rule.get("instance_id", ""))
        try:
            distance = df[plan.exit_distance_columns[instance_id]].astype(float)
        except KeyError as exc:
            raise InvalidRequestError(
                "missing ATR distance mapping for exit", instance_id=instance_id
            ) from exc
    elif component_id in _USD_DISTANCE_COMPONENTS:
        distance = pd.Series(_usd_distance(rule), index=df.index, dtype=float)
    else:
        raise InvalidRequestError("unsupported distance exit component", component_id=component_id)
    close = df["close"].astype(float)
    if (close <= 0).any():
        raise InvalidRequestError("exit distance ratio requires positive close")
    return distance.astype(float), (distance / close).astype(float)


def _profiles(
    records: tuple[ContextConsumptionRecord, ...], length: int
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    for record in records:
        if record.role == "exit_policy":
            assert record.profile_long is not None and record.profile_short is not None
            return record.raw_state, record.profile_long, record.profile_short
    neutral = tuple("neutral" for _ in range(length))
    return neutral, neutral, neutral


def _or(signals: list[pd.Series], index: pd.Index) -> pd.Series:
    output = pd.Series(False, index=index, dtype=bool)
    for signal in signals:
        output = output | signal.fillna(False).astype(bool)
    return output.astype(bool)


def _min(ratios: list[pd.Series], index: pd.Index) -> pd.Series:
    if not ratios:
        return pd.Series(float("nan"), index=index, dtype=float)
    return pd.concat(ratios, axis=1).min(axis=1).astype(float)


def _select(profile: tuple[str, ...], values: dict[str, pd.Series], index: pd.Index) -> pd.Series:
    # Positional gather, not label/index-aligned (design.md Decision 1):
    # np.column_stack/.to_numpy() strip pandas index alignment entirely, so
    # column `codes[i]` at row `i` is selected purely by bar position -- the
    # same guarantee the previous .iloc[position] loop gave, now structural
    # rather than incidental. _PROFILE_CODE[name] raises KeyError on an
    # unrecognized profile name, matching the prior values[name] KeyError --
    # deliberately not np.select(default=...), which would silently produce
    # a default value instead of failing closed.
    matrix = np.column_stack([values[name].to_numpy(dtype=float) for name in _PROFILE_ORDER])
    codes = np.fromiter(
        (_PROFILE_CODE[name] for name in profile), dtype=np.intp, count=len(profile)
    )
    selected = matrix[np.arange(len(profile)), codes]
    return pd.Series(selected, index=index, dtype=float)


def _select_bool(
    profile: tuple[str, ...], values: dict[str, pd.Series], index: pd.Index
) -> pd.Series:
    # Same positional gather as _select, bool dtype throughout -- see its
    # docstring comment for the positional/fail-closed rationale.
    matrix = np.column_stack([values[name].to_numpy(dtype=bool) for name in _PROFILE_ORDER])
    codes = np.fromiter(
        (_PROFILE_CODE[name] for name in profile), dtype=np.intp, count=len(profile)
    )
    selected = matrix[np.arange(len(profile)), codes]
    return pd.Series(selected, index=index, dtype=bool)


def _ready(sl: pd.Series, tp: pd.Series, sl_configured: bool, tp_configured: bool) -> pd.Series:
    output = pd.Series(True, index=sl.index, dtype=bool)
    if sl_configured:
        output = output & sl.notna()
    if tp_configured:
        output = output & tp.notna()
    return output


def _optional_floats(series: pd.Series) -> tuple[float | None, ...]:
    return tuple(None if pd.isna(value) else float(value) for value in series)


def _exit_rule_head(rule: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """Validated `(instance_id, component_id, exit_kind, family)` of one exit
    rule, `family` being "signal" or "distance" (shared by compute and
    resolve)."""

    instance_id = str(rule.get("instance_id", ""))
    component_id = str(rule.get("component_id", ""))
    exit_kind = str(rule.get("exit_kind", "signal"))
    if not instance_id:
        raise InvalidRequestError("exit rule requires instance_id")
    if component_id in _SIGNAL_COMPONENTS:
        if exit_kind != "signal":
            raise InvalidRequestError("signal exit component requires exit_kind signal")
        return instance_id, component_id, exit_kind, "signal"
    if component_id in _DISTANCE_COMPONENTS:
        expected_kind = "stop_loss" if "stop_loss" in component_id else "take_profit"
        if exit_kind != expected_kind:
            raise InvalidRequestError(
                "distance exit component has mismatched exit_kind",
                component_id=component_id,
                exit_kind=exit_kind,
            )
        return instance_id, component_id, exit_kind, "distance"
    raise InvalidRequestError("unsupported exit component", component_id=component_id)


@dataclass(frozen=True, slots=True)
class _ProfileSelection:
    """Instance ids each per-profile aggregate reads (always_on first, then
    the profile's own rules, in declared order)."""

    signal: tuple[str, ...]
    stop_loss: tuple[str, ...]
    take_profit: tuple[str, ...]
    stop_loss_configured: bool
    take_profit_configured: bool


def _profile_selection(
    groups: Mapping[str, tuple[Mapping[str, Any], ...]], profile: str
) -> _ProfileSelection:
    """Shared by compute and resolve."""

    selected = groups["always_on"] + groups[profile]
    return _ProfileSelection(
        signal=tuple(
            str(rule.get("instance_id"))
            for rule in selected
            if str(rule.get("exit_kind", "signal")) == "signal"
        ),
        stop_loss=tuple(
            str(rule.get("instance_id"))
            for rule in selected
            if str(rule.get("exit_kind")) == "stop_loss"
        ),
        take_profit=tuple(
            str(rule.get("instance_id"))
            for rule in selected
            if str(rule.get("exit_kind")) == "take_profit"
        ),
        stop_loss_configured=any(str(rule.get("exit_kind")) == "stop_loss" for rule in selected),
        take_profit_configured=any(
            str(rule.get("exit_kind")) == "take_profit" for rule in selected
        ),
    )


def _false_signal(index: pd.Index) -> pd.Series:
    """The all-False signal of a signal rule on a side that is not enabled."""

    return pd.Series(False, index=index, dtype=bool)


def _matches_rules(
    identities: ExitPolicyIdentity, groups: Mapping[str, tuple[Mapping[str, Any], ...]]
) -> bool:
    """True when `identities` is the resolved twin of exactly these rules:
    every rule's instance_id is present once, in its family's map, and no
    other instance_id is (duplicate ids would make the instance-keyed maps
    ambiguous, so they never memoize)."""

    signal: list[str] = []
    distance: list[str] = []
    for rules in groups.values():
        for rule in rules:
            instance_id = str(rule.get("instance_id", ""))
            component_id = str(rule.get("component_id", ""))
            (signal if component_id in _SIGNAL_COMPONENTS else distance).append(instance_id)
    return (
        len(set(signal) | set(distance)) == len(signal) + len(distance)
        and set(signal) == set(identities.signal_rules)
        and set(distance) == set(identities.distance_rules)
    )


def evaluate_exit_policy(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    consumption: tuple[ContextConsumptionRecord, ...],
    *,
    context: EvaluationContext | None = None,
    identities: ExitPolicyIdentity | None = None,
) -> ExitPolicyEvaluation:
    """`context` + `identities` (the `resolve_exit_policy` twin of this exact
    call; batch-computation-reuse 4.7): every exit-rule, per-profile
    aggregate and profile-select node is computed through the context's memo
    at the point it is computed today. Without them, everything computes
    directly.

    Nothing here reads setups, triggers or entries: the inputs are the
    frame (market columns + planned feature series), the exit rules, the
    enabled sides and the exit-profile consumption record only."""

    df = _frame_dataframe(frame)
    sides = _enabled_sides(raw_spec)
    groups = _policy_rules(raw_spec)
    if identities is not None and not _matches_rules(identities, groups):
        identities = None  # not this call's twin: never memoize on a mismatch
    ids = identities
    context_state, profile_long, profile_short = _profiles(consumption, len(df))
    signal_long_by_instance: dict[str, pd.Series] = {}
    signal_short_by_instance: dict[str, pd.Series] = {}
    distance_by_instance: dict[str, pd.Series] = {}
    ratio_by_instance: dict[str, pd.Series] = {}
    evidence: list[ExitRuleEvidence] = []

    for group, rules in groups.items():
        for rule in rules:
            instance_id, component_id, exit_kind, family = _exit_rule_head(rule)
            if family == "signal":
                for side in ("long", "short"):
                    signal_compute: functools.partial[pd.Series] = (
                        functools.partial(_signal_rule, df, rule, plan, side)
                        if side in sides
                        else functools.partial(_false_signal, df.index)
                    )
                    signal = compute_through(
                        context,
                        ids.signal_rules[instance_id][side] if ids else None,
                        signal_compute,
                    )
                    target = signal_long_by_instance if side == "long" else signal_short_by_instance
                    target[instance_id] = signal
                    if side in sides:
                        evidence.append(
                            ExitRuleEvidence(
                                instance_id,
                                component_id,
                                exit_kind,
                                group,
                                side,
                                tuple(bool(value) for value in signal),
                            )
                        )
            else:
                distance, ratio = compute_through(
                    context,
                    ids.distance_rules[instance_id] if ids else None,
                    functools.partial(_distance, df, rule, plan),
                )
                distance_by_instance[instance_id] = distance
                ratio_by_instance[instance_id] = ratio
                evidence.append(
                    ExitRuleEvidence(
                        instance_id,
                        component_id,
                        exit_kind,
                        group,
                        None,
                        distance_ratio=_optional_floats(ratio),
                    )
                )

    signals_long: dict[str, pd.Series] = {}
    signals_short: dict[str, pd.Series] = {}
    sl_by_profile: dict[str, pd.Series] = {}
    tp_by_profile: dict[str, pd.Series] = {}
    sl_distance_by_profile: dict[str, pd.Series] = {}
    tp_distance_by_profile: dict[str, pd.Series] = {}
    sl_configured_by_profile: dict[str, bool] = {}
    tp_configured_by_profile: dict[str, bool] = {}
    for profile in _PROFILE_ORDER:
        selection = _profile_selection(groups, profile)
        agg = ids.by_profile[profile] if ids else None
        sl_configured_by_profile[profile] = selection.stop_loss_configured
        tp_configured_by_profile[profile] = selection.take_profit_configured
        signals_long[profile] = compute_through(
            context,
            agg.signal_long if agg else None,
            functools.partial(
                _or,
                [signal_long_by_instance[instance_id] for instance_id in selection.signal],
                df.index,
            ),
        )
        signals_short[profile] = compute_through(
            context,
            agg.signal_short if agg else None,
            functools.partial(
                _or,
                [signal_short_by_instance[instance_id] for instance_id in selection.signal],
                df.index,
            ),
        )
        sl_by_profile[profile] = compute_through(
            context,
            agg.stop_loss_ratio if agg else None,
            functools.partial(
                _min,
                [ratio_by_instance[instance_id] for instance_id in selection.stop_loss],
                df.index,
            ),
        )
        tp_by_profile[profile] = compute_through(
            context,
            agg.take_profit_ratio if agg else None,
            functools.partial(
                _min,
                [ratio_by_instance[instance_id] for instance_id in selection.take_profit],
                df.index,
            ),
        )
        sl_distance_by_profile[profile] = compute_through(
            context,
            agg.stop_loss_distance if agg else None,
            functools.partial(
                _min,
                [distance_by_instance[instance_id] for instance_id in selection.stop_loss],
                df.index,
            ),
        )
        tp_distance_by_profile[profile] = compute_through(
            context,
            agg.take_profit_distance if agg else None,
            functools.partial(
                _min,
                [distance_by_instance[instance_id] for instance_id in selection.take_profit],
                df.index,
            ),
        )

    profile_by_side = {"long": profile_long, "short": profile_short}

    def select(
        field: str,
        side: str,
        function: Callable[[tuple[str, ...], dict[str, pd.Series], pd.Index], pd.Series],
        values: dict[str, pd.Series],
    ) -> pd.Series:
        return compute_through(
            context,
            ids.select[(field, side)] if ids else None,
            functools.partial(function, profile_by_side[side], values, df.index),
        )

    signal_long = select("signal", "long", _select_bool, signals_long)
    signal_short = select("signal", "short", _select_bool, signals_short)
    sl_long = select("stop_loss_ratio", "long", _select, sl_by_profile)
    sl_short = select("stop_loss_ratio", "short", _select, sl_by_profile)
    tp_long = select("take_profit_ratio", "long", _select, tp_by_profile)
    tp_short = select("take_profit_ratio", "short", _select, tp_by_profile)
    sl_distance_long = select("stop_loss_distance", "long", _select, sl_distance_by_profile)
    sl_distance_short = select("stop_loss_distance", "short", _select, sl_distance_by_profile)
    tp_distance_long = select("take_profit_distance", "long", _select, tp_distance_by_profile)
    tp_distance_short = select("take_profit_distance", "short", _select, tp_distance_by_profile)
    ready_by_profile = {
        profile: compute_through(
            context,
            ids.by_profile[profile].ready if ids else None,
            functools.partial(
                _ready,
                sl_by_profile[profile],
                tp_by_profile[profile],
                sl_configured_by_profile[profile],
                tp_configured_by_profile[profile],
            ),
        )
        for profile in _PROFILE_ORDER
    }
    ready_long = select("ready", "long", _select_bool, ready_by_profile)
    ready_short = select("ready", "short", _select_bool, ready_by_profile)
    return ExitPolicyEvaluation(
        context_state=context_state,
        profile_long=profile_long,
        profile_short=profile_short,
        signal_exit_long=tuple(bool(value) for value in signal_long),
        signal_exit_short=tuple(bool(value) for value in signal_short),
        stop_loss_ratio_long=_optional_floats(sl_long),
        stop_loss_ratio_short=_optional_floats(sl_short),
        take_profit_ratio_long=_optional_floats(tp_long),
        take_profit_ratio_short=_optional_floats(tp_short),
        stop_loss_distance_long=_optional_floats(sl_distance_long),
        stop_loss_distance_short=_optional_floats(sl_distance_short),
        take_profit_distance_long=_optional_floats(tp_distance_long),
        take_profit_distance_short=_optional_floats(tp_distance_short),
        stop_ready_long=tuple(bool(value) for value in ready_long),
        stop_ready_short=tuple(bool(value) for value in ready_short),
        signal_by_profile_long={
            key: tuple(bool(value) for value in item) for key, item in signals_long.items()
        },
        signal_by_profile_short={
            key: tuple(bool(value) for value in item) for key, item in signals_short.items()
        },
        stop_loss_by_profile={
            key: _optional_floats(item) for key, item in sl_by_profile.items()
        },
        take_profit_by_profile={
            key: _optional_floats(item) for key, item in tp_by_profile.items()
        },
        rule_evidence=tuple(evidence),
    )


# -- semantic node identity (batch-computation-reuse group 3) -----------------
#
# Node families: per-rule numeric evaluation (signal per side, distance
# side-free), per-profile aggregates (OR / min / ready), and profile-select
# (positional gather by the per-bar profile). Declared rule order, group
# placement and instance_id are labels for evidence/attribution only: every
# aggregate is a commutative, idempotent reduction (OR, NaN-skipping min),
# so its upstream is an order/duplicate-insensitive set of rule identities.

EXIT_NODE_VERSION = 1


def _feature_node(feature_ids: Mapping[str, NodeSpec], output_id: str) -> NodeSpec:
    """Identity of the frame column `_frame_dataframe` builds from a plan
    label (fails closed, like the `df[...]` lookup it mirrors)."""

    try:
        return feature_ids[output_id]
    except KeyError as exc:
        raise InvalidRequestError("missing planned feature series", output_id=output_id) from exc


def constant_false_signal() -> NodeSpec:
    """All-False signal: `no_signal_exit`, and any signal rule on a side that
    is not enabled (compute emits the identical all-False series)."""

    return node_spec("exit.signal.constant_false", version=EXIT_NODE_VERSION)


def resolve_signal_rule(
    rule: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    side: str,
) -> NodeSpec:
    """Identity of `_signal_rule(df, rule, plan, side)` for an enabled side."""

    component_id = str(rule.get("component_id", ""))
    kind = f"exit.signal.{component_id}"
    if component_id == "no_signal_exit":
        return constant_false_signal()
    if component_id == "rsi_signal_exit":
        key = _rsi_exit_key(rule)
        output_id = plan.rsi_columns.get(key)
        if output_id is None or output_id not in feature_ids:
            raise InvalidRequestError("missing RSI mapping for exit")
        return node_spec(
            kind,
            version=EXIT_NODE_VERSION,
            params={"threshold": _rsi_exit_threshold(rule, side)},
            upstream={"rsi": feature_ids[output_id]},
            side=side,
        )
    if component_id == "ema_close_loss_exit":
        ema = _feature_node(feature_ids, _ema_column(rule.get("ema"), plan, "exit.ema"))
        confirm_bars = _confirm_bars(rule)
        _require_confirm_bars(confirm_bars)
        return node_spec(
            kind,
            version=EXIT_NODE_VERSION,
            params={"confirm_bars": confirm_bars},
            upstream={"ema": ema},
            side=side,
        )
    if component_id == "ema_cross_loss_exit":
        fast = _feature_node(
            feature_ids, _ema_column(rule.get("fast_ema"), plan, "exit.fast_ema")
        )
        slow = _feature_node(
            feature_ids, _ema_column(rule.get("slow_ema"), plan, "exit.slow_ema")
        )
        confirm_bars = _confirm_bars(rule)
        _require_confirm_bars(confirm_bars)  # compute: 1 short-circuits, < 1 raises
        return node_spec(
            kind,
            version=EXIT_NODE_VERSION,
            params={"confirm_bars": confirm_bars},
            upstream={"fast": fast, "slow": slow},
            side=side,
        )
    raise InvalidRequestError("unsupported signal exit component", component_id=component_id)


def resolve_distance_rule(
    rule: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
) -> NodeSpec:
    """Identity of `_distance(df, rule, plan)` -> `(distance, ratio)`.

    Side-free. Stop-loss vs take-profit is not an input of this computation
    (both components run the same code); the aggregates select by
    `exit_kind`. The ATR variant's upstream is the identity of the column
    `plan.exit_distance_columns[instance_id]` names -- exactly the series the
    compute reads."""

    component_id = str(rule.get("component_id", ""))
    if component_id in _ATR_DISTANCE_COMPONENTS:
        instance_id = str(rule.get("instance_id", ""))
        output_id = plan.exit_distance_columns.get(instance_id)
        if output_id is None or output_id not in feature_ids:
            raise InvalidRequestError(
                "missing ATR distance mapping for exit", instance_id=instance_id
            )
        return node_spec(
            "exit.distance.atr",
            version=EXIT_NODE_VERSION,
            upstream={"distance": feature_ids[output_id]},
        )
    if component_id in _USD_DISTANCE_COMPONENTS:
        return node_spec(
            "exit.distance.constant_usd",
            version=EXIT_NODE_VERSION,
            params={"usd_distance": _usd_distance(rule)},
        )
    raise InvalidRequestError("unsupported distance exit component", component_id=component_id)


def _aggregate(kind: str, rules: tuple[NodeSpec, ...]) -> NodeSpec:
    return node_spec(kind, version=EXIT_NODE_VERSION, upstream={"rules": rules})


@dataclass(frozen=True, slots=True)
class ProfileAggregateIdentity:
    """Per-profile aggregate identities (`signals_long/short[profile]`,
    `sl/tp_by_profile`, `sl/tp_distance_by_profile`, `ready_by_profile`)."""

    signal_long: NodeSpec
    signal_short: NodeSpec
    stop_loss_ratio: NodeSpec
    take_profit_ratio: NodeSpec
    stop_loss_distance: NodeSpec
    take_profit_distance: NodeSpec
    ready: NodeSpec


@dataclass(frozen=True, slots=True)
class ExitPolicyIdentity:
    """Identity twin of `ExitPolicyEvaluation`'s numeric fields.

    `rules` maps each rule's instance_id label to its per-side signal
    identities (signal rules) or its side-free distance identity. `select`
    maps `(field, side)` to a profile-select identity, `field` in
    signal/stop_loss_ratio/take_profit_ratio/stop_loss_distance/
    take_profit_distance/ready."""

    context_state: NodeSpec | None
    profile_long: NodeSpec
    profile_short: NodeSpec
    signal_rules: dict[str, dict[str, NodeSpec]]
    distance_rules: dict[str, NodeSpec]
    by_profile: dict[str, ProfileAggregateIdentity]
    select: dict[tuple[str, str], NodeSpec]


def _select_node(kind: str, profile: NodeSpec, values: Mapping[str, NodeSpec]) -> NodeSpec:
    """Identity of `_select`/`_select_bool`: positional gather by the per-bar
    profile series. Side is not read -- it enters only through `profile`."""

    return node_spec(
        kind,
        version=EXIT_NODE_VERSION,
        upstream={"profile": profile, **{name: values[name] for name in _PROFILE_ORDER}},
    )


def resolve_exit_policy(
    raw_spec: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    context_ids: Mapping[str, NodeSpec],
) -> ExitPolicyIdentity:
    """Identity twin of `evaluate_exit_policy`."""

    sides = _enabled_sides(raw_spec)
    groups = _policy_rules(raw_spec)
    context_state, profile_long, profile_short = resolve_exit_profiles(raw_spec, context_ids)
    signal_rules: dict[str, dict[str, NodeSpec]] = {}
    distance_rules: dict[str, NodeSpec] = {}
    for _group, rules in groups.items():
        for rule in rules:
            instance_id, _component_id, _exit_kind, family = _exit_rule_head(rule)
            if family == "signal":
                signal_rules[instance_id] = {
                    side: (
                        resolve_signal_rule(rule, plan, feature_ids, side)
                        if side in sides
                        else constant_false_signal()
                    )
                    for side in ("long", "short")
                }
            else:
                distance_rules[instance_id] = resolve_distance_rule(rule, plan, feature_ids)

    by_profile: dict[str, ProfileAggregateIdentity] = {}
    for profile in _PROFILE_ORDER:
        selection = _profile_selection(groups, profile)
        stop_loss_rules = tuple(distance_rules[item] for item in selection.stop_loss)
        take_profit_rules = tuple(distance_rules[item] for item in selection.take_profit)
        stop_loss_ratio = _aggregate("exit.aggregate.min_ratio", stop_loss_rules)
        take_profit_ratio = _aggregate("exit.aggregate.min_ratio", take_profit_rules)
        by_profile[profile] = ProfileAggregateIdentity(
            signal_long=_aggregate(
                "exit.aggregate.any_signal",
                tuple(signal_rules[item]["long"] for item in selection.signal),
            ),
            signal_short=_aggregate(
                "exit.aggregate.any_signal",
                tuple(signal_rules[item]["short"] for item in selection.signal),
            ),
            stop_loss_ratio=stop_loss_ratio,
            take_profit_ratio=take_profit_ratio,
            stop_loss_distance=_aggregate("exit.aggregate.min_distance", stop_loss_rules),
            take_profit_distance=_aggregate("exit.aggregate.min_distance", take_profit_rules),
            ready=node_spec(
                "exit.aggregate.ready",
                version=EXIT_NODE_VERSION,
                params={
                    "stop_loss_configured": selection.stop_loss_configured,
                    "take_profit_configured": selection.take_profit_configured,
                },
                upstream={"stop_loss": stop_loss_ratio, "take_profit": take_profit_ratio},
            ),
        )

    select: dict[tuple[str, str], NodeSpec] = {}
    for side, profile_node in (("long", profile_long), ("short", profile_short)):
        select[("signal", side)] = _select_node(
            "exit.select_bool",
            profile_node,
            {
                name: (item.signal_long if side == "long" else item.signal_short)
                for name, item in by_profile.items()
            },
        )
        for field in (
            "stop_loss_ratio",
            "take_profit_ratio",
            "stop_loss_distance",
            "take_profit_distance",
        ):
            select[(field, side)] = _select_node(
                "exit.select_float",
                profile_node,
                {name: getattr(item, field) for name, item in by_profile.items()},
            )
        select[("ready", side)] = _select_node(
            "exit.select_bool",
            profile_node,
            {name: item.ready for name, item in by_profile.items()},
        )
    return ExitPolicyIdentity(
        context_state=context_state,
        profile_long=profile_long,
        profile_short=profile_short,
        signal_rules=signal_rules,
        distance_rules=distance_rules,
        by_profile=by_profile,
        select=select,
    )


# -- memoized exit nodes (batch-computation-reuse 4.7) ---------------------------


def resolve_memoized_exit_policy(
    raw_spec: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
    context_ids: Mapping[str, NodeSpec],
) -> ExitPolicyIdentity | None:
    """`resolve_exit_policy`, or `None` when its identities cannot key this
    spec's exit nodes unambiguously (duplicate instance_ids): exit nodes then
    compute directly, unmemoized. Raises whatever resolution raises."""

    identities = resolve_exit_policy(raw_spec, plan, feature_ids, context_ids)
    if not _matches_rules(identities, _policy_rules(raw_spec)):
        return None
    return identities


def exit_policy_consumptions(identities: ExitPolicyIdentity) -> tuple[NodeSpec, ...]:
    """Every memo consumption `evaluate_exit_policy` makes with these
    identities (design.md D5 pre-pass): each signal rule once per side (a
    disabled side consumes the constant all-False signal), each distance
    rule once, then per profile its six OR/min aggregates, then the ten
    signal/ratio/distance profile-selects, the three per-profile `ready`
    aggregates and the two `ready` selects."""

    consumed: list[NodeSpec] = []
    for per_side in identities.signal_rules.values():
        consumed += (per_side["long"], per_side["short"])
    consumed += identities.distance_rules.values()
    for profile in _PROFILE_ORDER:
        aggregate = identities.by_profile[profile]
        consumed += (
            aggregate.signal_long,
            aggregate.signal_short,
            aggregate.stop_loss_ratio,
            aggregate.take_profit_ratio,
            aggregate.stop_loss_distance,
            aggregate.take_profit_distance,
        )
    for field in (
        "signal",
        "stop_loss_ratio",
        "take_profit_ratio",
        "stop_loss_distance",
        "take_profit_distance",
    ):
        consumed += (identities.select[(field, "long")], identities.select[(field, "short")])
    consumed += (identities.by_profile[profile].ready for profile in _PROFILE_ORDER)
    consumed += (identities.select[("ready", "long")], identities.select[("ready", "short")])
    return tuple(consumed)
