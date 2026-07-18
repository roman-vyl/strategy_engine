"""BBB-compatible profile-aware exit policy evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from typing import Any

import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.values import normalized_decimal_text
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.context_consumption import (
    ContextConsumptionRecord,
)
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan

_PROFILE_ORDER = ("aligned", "countertrend", "neutral")
_SIGNAL_COMPONENTS = {
    "no_signal_exit",
    "rsi_signal_exit",
    "ema_close_loss_exit",
    "ema_cross_loss_exit",
}
_DISTANCE_COMPONENTS = {
    "atr_stop_loss",
    "atr_take_profit",
    "constant_usd_stop_loss",
    "constant_usd_take_profit",
}


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


def _frame_dataframe(frame: FeatureFrame) -> pd.DataFrame:
    if len(frame.market_bars) != len(frame.time_ms):
        raise InvalidRequestError("market bars unavailable for exit policy")
    index = pd.to_datetime(frame.time_ms, unit="ms", utc=True)
    data: dict[str, object] = {
        "open": [float(bar.open) for bar in frame.market_bars],
        "high": [float(bar.high) for bar in frame.market_bars],
        "low": [float(bar.low) for bar in frame.market_bars],
        "close": [float(bar.close) for bar in frame.market_bars],
        "volume": [float(bar.volume) for bar in frame.market_bars],
    }
    for output_id, values in frame.series.items():
        data[output_id] = [float("nan") if value is None else float(value) for value in values]
    return pd.DataFrame(data, index=index)


def _ema_column(raw: object, plan: EmaPullbackFeaturePlan, path: str) -> str:
    payload = _mapping(raw, path)
    timeframe = str(payload.get("timeframe", "base"))
    period = int(payload.get("period"))
    try:
        return plan.ema_columns[(timeframe, period)]
    except KeyError as exc:
        raise InvalidRequestError("missing EMA mapping for exit", path=path) from exc


def _consecutive_true(condition: pd.Series, confirm_bars: int) -> pd.Series:
    if confirm_bars < 1:
        raise InvalidRequestError("confirm_bars must be >= 1")
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
        rsi = _mapping(rule.get("rsi"), "exit.rsi")
        key = (str(rsi.get("timeframe", "base")), int(rsi.get("period", 14)))
        try:
            values = df[plan.rsi_columns[key]].astype(float)
        except KeyError as exc:
            raise InvalidRequestError("missing RSI mapping for exit") from exc
        if side == "long":
            threshold = rule.get("long_exit_above")
            if threshold is None:
                raise InvalidRequestError("rsi_signal_exit requires long_exit_above")
            return (values > float(threshold)).fillna(False).astype(bool)
        threshold = rule.get("short_exit_below")
        if threshold is None:
            raise InvalidRequestError("rsi_signal_exit requires short_exit_below")
        return (values < float(threshold)).fillna(False).astype(bool)
    if component_id == "ema_close_loss_exit":
        ema = df[_ema_column(rule.get("ema"), plan, "exit.ema")].astype(float)
        close = df["close"].astype(float)
        condition = close < ema if side == "long" else close > ema
        return _consecutive_true(condition, int(rule.get("confirm_bars", 1)))
    if component_id == "ema_cross_loss_exit":
        fast = df[_ema_column(rule.get("fast_ema"), plan, "exit.fast_ema")].astype(float)
        slow = df[_ema_column(rule.get("slow_ema"), plan, "exit.slow_ema")].astype(float)
        confirm_bars = int(rule.get("confirm_bars", 1))
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


def _distance(
    df: pd.DataFrame,
    rule: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
) -> tuple[pd.Series, pd.Series]:
    component_id = str(rule.get("component_id", ""))
    if component_id in {"atr_stop_loss", "atr_take_profit"}:
        instance_id = str(rule.get("instance_id", ""))
        try:
            distance = df[plan.exit_distance_columns[instance_id]].astype(float)
        except KeyError as exc:
            raise InvalidRequestError(
                "missing ATR distance mapping for exit", instance_id=instance_id
            ) from exc
    elif component_id in {"constant_usd_stop_loss", "constant_usd_take_profit"}:
        raw_distance = rule.get("usd_distance")
        if raw_distance is None:
            raise InvalidRequestError("constant USD exit requires usd_distance")
        distance = pd.Series(float(raw_distance), index=df.index, dtype=float)
    else:
        raise InvalidRequestError("unsupported distance exit component", component_id=component_id)
    close = df["close"].astype(float)
    if (close <= 0).any():
        raise InvalidRequestError("exit distance ratio requires positive close")
    return distance.astype(float), (distance / close).astype(float)


def _policy_rules(raw_spec: Mapping[str, Any]) -> dict[str, tuple[Mapping[str, Any], ...]]:
    trade_management = _mapping(raw_spec.get("trade_management", {}), "trade_management")
    exit_policy = _mapping(trade_management.get("exit_policy", {}), "exit_policy")
    always = _mapping(exit_policy.get("always_on", {}), "exit_policy.always_on")
    profiles = _mapping(exit_policy.get("profiles", {}), "exit_policy.profiles")
    result = {"always_on": _list(always.get("exits", []), "always_on.exits")}
    for profile in _PROFILE_ORDER:
        payload = _mapping(profiles.get(profile, {}), f"exit_policy.profiles.{profile}")
        result[profile] = _list(payload.get("exits", []), f"profiles.{profile}.exits")
    return result


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
    output = pd.Series(float("nan"), index=index, dtype=float)
    for position, name in enumerate(profile):
        output.iloc[position] = values[name].iloc[position]
    return output


def _select_bool(
    profile: tuple[str, ...], values: dict[str, pd.Series], index: pd.Index
) -> pd.Series:
    output = pd.Series(False, index=index, dtype=bool)
    for position, name in enumerate(profile):
        output.iloc[position] = bool(values[name].iloc[position])
    return output


def _ready(sl: pd.Series, tp: pd.Series) -> pd.Series:
    output = pd.Series(True, index=sl.index, dtype=bool)
    if sl.notna().any():
        output = output & sl.notna()
    if tp.notna().any():
        output = output & tp.notna()
    return output


def _optional_floats(series: pd.Series) -> tuple[float | None, ...]:
    return tuple(None if pd.isna(value) else float(value) for value in series)


def evaluate_exit_policy(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    consumption: tuple[ContextConsumptionRecord, ...],
) -> ExitPolicyEvaluation:
    df = _frame_dataframe(frame)
    sides = _enabled_sides(raw_spec)
    groups = _policy_rules(raw_spec)
    context_state, profile_long, profile_short = _profiles(consumption, len(df))
    signal_long_by_instance: dict[str, pd.Series] = {}
    signal_short_by_instance: dict[str, pd.Series] = {}
    distance_by_instance: dict[str, pd.Series] = {}
    ratio_by_instance: dict[str, pd.Series] = {}
    evidence: list[ExitRuleEvidence] = []

    for group, rules in groups.items():
        for rule in rules:
            instance_id = str(rule.get("instance_id", ""))
            component_id = str(rule.get("component_id", ""))
            exit_kind = str(rule.get("exit_kind", "signal"))
            if not instance_id:
                raise InvalidRequestError("exit rule requires instance_id")
            if component_id in _SIGNAL_COMPONENTS:
                if exit_kind != "signal":
                    raise InvalidRequestError("signal exit component requires exit_kind signal")
                for side in ("long", "short"):
                    signal = (
                        _signal_rule(df, rule, plan, side)
                        if side in sides
                        else pd.Series(False, index=df.index, dtype=bool)
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
            elif component_id in _DISTANCE_COMPONENTS:
                expected_kind = "stop_loss" if "stop_loss" in component_id else "take_profit"
                if exit_kind != expected_kind:
                    raise InvalidRequestError(
                        "distance exit component has mismatched exit_kind",
                        component_id=component_id,
                        exit_kind=exit_kind,
                    )
                distance, ratio = _distance(df, rule, plan)
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
            else:
                raise InvalidRequestError("unsupported exit component", component_id=component_id)

    signals_long: dict[str, pd.Series] = {}
    signals_short: dict[str, pd.Series] = {}
    sl_by_profile: dict[str, pd.Series] = {}
    tp_by_profile: dict[str, pd.Series] = {}
    sl_distance_by_profile: dict[str, pd.Series] = {}
    tp_distance_by_profile: dict[str, pd.Series] = {}
    always = groups["always_on"]
    for profile in _PROFILE_ORDER:
        selected = always + groups[profile]
        signal_rules = [
            rule for rule in selected if str(rule.get("exit_kind", "signal")) == "signal"
        ]
        signals_long[profile] = _or(
            [signal_long_by_instance[str(rule.get("instance_id"))] for rule in signal_rules],
            df.index,
        )
        signals_short[profile] = _or(
            [signal_short_by_instance[str(rule.get("instance_id"))] for rule in signal_rules],
            df.index,
        )
        sl_by_profile[profile] = _min(
            [
                ratio_by_instance[str(rule.get("instance_id"))]
                for rule in selected
                if str(rule.get("exit_kind")) == "stop_loss"
            ],
            df.index,
        )
        tp_by_profile[profile] = _min(
            [
                ratio_by_instance[str(rule.get("instance_id"))]
                for rule in selected
                if str(rule.get("exit_kind")) == "take_profit"
            ],
            df.index,
        )
        sl_distance_by_profile[profile] = _min(
            [
                distance_by_instance[str(rule.get("instance_id"))]
                for rule in selected
                if str(rule.get("exit_kind")) == "stop_loss"
            ],
            df.index,
        )
        tp_distance_by_profile[profile] = _min(
            [
                distance_by_instance[str(rule.get("instance_id"))]
                for rule in selected
                if str(rule.get("exit_kind")) == "take_profit"
            ],
            df.index,
        )

    signal_long = _select_bool(profile_long, signals_long, df.index)
    signal_short = _select_bool(profile_short, signals_short, df.index)
    sl_long = _select(profile_long, sl_by_profile, df.index)
    sl_short = _select(profile_short, sl_by_profile, df.index)
    tp_long = _select(profile_long, tp_by_profile, df.index)
    tp_short = _select(profile_short, tp_by_profile, df.index)
    sl_distance_long = _select(profile_long, sl_distance_by_profile, df.index)
    sl_distance_short = _select(profile_short, sl_distance_by_profile, df.index)
    tp_distance_long = _select(profile_long, tp_distance_by_profile, df.index)
    tp_distance_short = _select(profile_short, tp_distance_by_profile, df.index)
    ready_by_profile = {
        profile: _ready(sl_by_profile[profile], tp_by_profile[profile])
        for profile in _PROFILE_ORDER
    }
    ready_long = _select_bool(profile_long, ready_by_profile, df.index)
    ready_short = _select_bool(profile_short, ready_by_profile, df.index)
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
