"""Pure managed-exit policy replay for one already-open trade."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from math import isfinite
from typing import Any, Literal

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.values import normalized_decimal_text
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan

_PHASES = ("initial_risk", "proven", "protected", "runner", "exhaustion")
Side = Literal["long", "short"]


@dataclass(slots=True)
class ManagedTradeState:
    trade_id: str
    side: Side
    entry_index: int
    entry_time_ms: int
    entry_price: float
    bars_in_trade: int = 0
    phase: str = "initial_risk"
    max_phase_reached: str = "initial_risk"
    best_price: float = 0.0
    worst_price: float = 0.0
    mfe_price: float = 0.0
    mfe_pct: float = 0.0
    mae_price: float = 0.0
    mae_pct: float = 0.0
    active_stop_price: float | None = None
    active_stop_rule_id: str | None = None
    active_stop_component_id: str | None = None
    active_take_profile: str = "initial"
    active_take_rule_id: str | None = None
    active_take_component_id: str | None = None
    active_runtime_exit_rules: tuple[str, ...] = ()

    @classmethod
    def initial(
        cls,
        *,
        trade_id: str,
        side: Side,
        entry_index: int,
        entry_time_ms: int,
        entry_price: float,
    ) -> ManagedTradeState:
        return cls(
            trade_id=trade_id,
            side=side,
            entry_index=entry_index,
            entry_time_ms=entry_time_ms,
            entry_price=entry_price,
            best_price=entry_price,
            worst_price=entry_price,
            mfe_price=entry_price,
            mae_price=entry_price,
        )


@dataclass(frozen=True, slots=True)
class ManagedPolicyEvent:
    time_ms: int
    bar_index: int
    event_type: str
    rule_id: str | None
    component_id: str | None
    from_phase: str | None = None
    to_phase: str | None = None
    price: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_wire(self) -> dict[str, object]:
        return {
            "time_ms": self.time_ms,
            "bar_index": self.bar_index,
            "event_type": self.event_type,
            "rule_id": self.rule_id,
            "component_id": self.component_id,
            "from_phase": self.from_phase,
            "to_phase": self.to_phase,
            "price": _text(self.price),
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ManagedBarDecision:
    time_ms: int
    bar_index: int
    phase: str
    bars_in_trade: int
    mfe_pct: float
    mae_pct: float
    active_stop_price: float | None
    active_take_profile: str
    runtime_exit_rule_ids: tuple[str, ...]
    effective_from_time_ms: int | None

    def to_wire(self) -> dict[str, object]:
        return {
            "time_ms": self.time_ms,
            "bar_index": self.bar_index,
            "phase": self.phase,
            "bars_in_trade": self.bars_in_trade,
            "mfe_pct": _text(self.mfe_pct),
            "mae_pct": _text(self.mae_pct),
            "active_stop_price": _text(self.active_stop_price),
            "active_take_profile": self.active_take_profile,
            "runtime_exit_rule_ids": list(self.runtime_exit_rule_ids),
            "effective_from_time_ms": self.effective_from_time_ms,
        }


@dataclass(frozen=True, slots=True)
class ManagedReplayResult:
    trade_id: str
    side: Side
    entry_time_ms: int
    events: tuple[ManagedPolicyEvent, ...]
    bars: tuple[ManagedBarDecision, ...]
    final_state: ManagedTradeState

    def to_wire(self) -> dict[str, object]:
        state = self.final_state
        return {
            "contract_version": "managed_policy_replay.v1",
            "decision_timing": "end_of_bar_effective_next_bar",
            "trade_id": self.trade_id,
            "side": self.side,
            "entry_time_ms": self.entry_time_ms,
            "events": [event.to_wire() for event in self.events],
            "bars": [bar.to_wire() for bar in self.bars],
            "final_state": {
                "phase": state.phase,
                "max_phase_reached": state.max_phase_reached,
                "bars_in_trade": state.bars_in_trade,
                "mfe_pct": _text(state.mfe_pct),
                "mae_pct": _text(state.mae_pct),
                "active_stop_price": _text(state.active_stop_price),
                "active_stop_rule_id": state.active_stop_rule_id,
                "active_stop_component_id": state.active_stop_component_id,
                "active_take_profile": state.active_take_profile,
                "active_take_rule_id": state.active_take_rule_id,
                "active_take_component_id": state.active_take_component_id,
                "active_runtime_exit_rules": list(state.active_runtime_exit_rules),
            },
        }


@dataclass(frozen=True, slots=True)
class StartAfterEntryManagedProjection:
    """Internal open-trade projection with exact receipt-seeded protection."""

    replay: ManagedReplayResult
    desired_stop_price: Decimal
    desired_take_price: Decimal | None


def _text(value: float | None) -> str | None:
    if value is None or not isfinite(value):
        return None
    return normalized_decimal_text(Decimal(str(value)))


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _items(value: Any, path: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise InvalidRequestError(f"{path} must be a list")
    return tuple(_mapping(item, f"{path}[]") for item in value)


def _rank(phase: str) -> int:
    try:
        return _PHASES.index(phase)
    except ValueError as exc:
        raise InvalidRequestError("unknown trade-management phase", phase=phase) from exc


def _at_least(current: str, threshold: str) -> bool:
    return _rank(current) >= _rank(threshold)


def _float(value: Any, path: str, *, positive: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidRequestError(f"{path} must be numeric") from exc
    if not isfinite(result) or (positive and result <= 0):
        raise InvalidRequestError(f"{path} must be finite" + (" and positive" if positive else ""))
    return result


def _int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidRequestError(f"{path} must be an integer >= 1")
    return int(value)


def _series(frame: FeatureFrame, output_id: str) -> tuple[float | None, ...]:
    values = frame.series.get(output_id)
    if values is None:
        return tuple(None for _ in frame.time_ms)
    return tuple(None if value is None else float(value) for value in values)


def _atr_output_id(plan: EmaPullbackFeaturePlan, timeframe: str, period: int) -> str | None:
    for feature in plan.indicator_plan.features:
        if (
            feature.kind == "atr"
            and feature.timeframe == timeframe
            and int(feature.parameters.get("period", 0)) == period
        ):
            return feature.output_id
    return None


def _feature_value(frame: FeatureFrame, output_id: str | None, index: int) -> float | None:
    if output_id is None:
        return None
    values = _series(frame, output_id)
    if not (0 <= index < len(values)):
        return None
    return values[index]


def _update_extremes(state: ManagedTradeState, *, index: int, high: float, low: float) -> None:
    state.bars_in_trade = index - state.entry_index + 1
    if state.side == "long":
        state.best_price = max(state.best_price, high)
        state.worst_price = min(state.worst_price, low)
        state.mfe_price = state.best_price
        state.mae_price = state.worst_price
        state.mfe_pct = (state.best_price - state.entry_price) / state.entry_price
        state.mae_pct = (state.entry_price - state.worst_price) / state.entry_price
    else:
        state.best_price = min(state.best_price, low)
        state.worst_price = max(state.worst_price, high)
        state.mfe_price = state.best_price
        state.mae_price = state.worst_price
        state.mfe_pct = (state.entry_price - state.best_price) / state.entry_price
        state.mae_pct = (state.worst_price - state.entry_price) / state.entry_price


def _phase_met(
    condition: Mapping[str, Any],
    *,
    state: ManagedTradeState,
    index: int,
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
) -> tuple[bool, dict[str, object]]:
    component_id = str(condition.get("component_id", ""))
    params = _mapping(condition.get("params", {}), "phase condition params")
    if component_id == "bars_in_trade":
        bars_threshold = _int(params.get("threshold"), "bars_in_trade.threshold")
        return state.bars_in_trade >= bars_threshold, {"threshold": bars_threshold}
    if component_id == "mfe_pct":
        pct_threshold = _float(params.get("threshold"), "mfe_pct.threshold", positive=True)
        return state.mfe_pct >= pct_threshold, {"threshold": pct_threshold}
    if component_id == "mfe_atr":
        atr_threshold = _float(params.get("threshold"), "mfe_atr.threshold", positive=True)
        atr = _mapping(params.get("atr"), "mfe_atr.atr")
        key = (str(atr.get("timeframe", "")), _int(atr.get("period"), "mfe_atr.atr.period"))
        output_id = _atr_output_id(plan, key[0], key[1])
        value = _feature_value(frame, output_id, index)
        if value is None or value <= 0:
            return False, {"reason": "indicator_not_ready"}
        distance = abs(state.mfe_price - state.entry_price)
        return distance >= atr_threshold * value, {"threshold": atr_threshold, "atr": value}
    if component_id == "adx_di_threshold":
        key = (
            str(params.get("timeframe", "")),
            _int(params.get("period"), "adx_di_threshold.period"),
        )
        columns = plan.adx_dmi_columns.get(key, {})
        adx = _feature_value(frame, columns.get("adx"), index)
        plus = _feature_value(frame, columns.get("di_plus"), index)
        minus = _feature_value(frame, columns.get("di_minus"), index)
        if adx is None or plus is None or minus is None:
            return False, {"reason": "indicator_not_ready"}
        adx_threshold = _float(
            params.get("adx_threshold"), "adx_di_threshold.adx_threshold", positive=True
        )
        aligned = plus > minus if state.side == "long" else minus > plus
        require = params.get("require_di_alignment", True)
        if not isinstance(require, bool):
            raise InvalidRequestError("require_di_alignment must be boolean")
        return adx >= adx_threshold and (not require or aligned), {
            "adx": adx,
            "di_plus": plus,
            "di_minus": minus,
            "di_aligned": aligned,
        }
    raise InvalidRequestError("unsupported phase condition", component_id=component_id)


def _runtime_signal(
    rule: Mapping[str, Any],
    *,
    state: ManagedTradeState,
    index: int,
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    evaluation_start_index: int,
) -> bool:
    component_id = str(rule.get("component_id", ""))
    params = _mapping(rule.get("params", {}), "runtime exit params")
    if component_id == "phase_runtime_exit":
        return str(params.get("exit_price", "close")) == "close"
    confirm = int(params.get("confirm_bars", 1))
    start = index - confirm + 1
    if start < evaluation_start_index:
        return False
    if component_id == "rsi_signal_exit":
        rsi = _mapping(params.get("rsi"), "runtime rsi")
        output = plan.rsi_columns.get((str(rsi.get("timeframe", "")), int(rsi.get("period", 0))))
        values = _series(frame, output or "")
        threshold = (
            params.get("long_exit_above")
            if state.side == "long"
            else params.get("short_exit_below")
        )
        if threshold is None:
            return False
        boundary = float(threshold)
        window = values[start : index + 1]
        return all(
            value is not None and (value >= boundary if state.side == "long" else value <= boundary)
            for value in window
        )
    if component_id == "ema_cross_loss_exit":
        fast = _mapping(params.get("fast_ema"), "runtime fast_ema")
        slow = _mapping(params.get("slow_ema"), "runtime slow_ema")
        fast_id = plan.ema_columns.get((str(fast.get("timeframe", "")), int(fast.get("period", 0))))
        slow_id = plan.ema_columns.get((str(slow.get("timeframe", "")), int(slow.get("period", 0))))
        fast_values = _series(frame, fast_id or "")
        slow_values = _series(frame, slow_id or "")
        for pos in range(start, index + 1):
            fast_value = fast_values[pos]
            slow_value = slow_values[pos]
            if fast_value is None or slow_value is None:
                return False
            crossed = fast_value <= slow_value if state.side == "long" else fast_value >= slow_value
            if not crossed:
                return False
        return True
    raise InvalidRequestError("unsupported runtime exit component", component_id=component_id)


def _evaluate_managed_replay_core(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    *,
    trade_id: str,
    side: Side,
    entry_time_ms: int,
    entry_price: float,
    evaluation_start_offset: int,
    initial_stop_price: float | None = None,
    target_index: int | None = None,
    require_managed_mode: bool = True,
) -> ManagedReplayResult:
    management = _mapping(raw_spec.get("trade_management", {}), "trade_management")
    config = _mapping(management.get("exit_management", {}), "exit_management")
    if require_managed_mode and config.get("mode") != "managed":
        raise InvalidRequestError("managed replay requires exit_management.mode='managed'")
    try:
        entry_index = frame.time_ms.index(entry_time_ms)
    except ValueError as exc:
        raise InvalidRequestError("entry_time_ms is not on the evaluation grid") from exc
    if entry_price <= 0:
        raise InvalidRequestError("entry_price must be positive")
    phase_rules = _items(config.get("phase_rules", ()), "phase_rules")
    stop_rules = _items(config.get("stop_management", ()), "stop_management")
    take_rules = _items(config.get("take_management", ()), "take_management")
    runtime_rules = _items(config.get("runtime_exits", ()), "runtime_exits")
    state = ManagedTradeState.initial(
        trade_id=trade_id,
        side=side,
        entry_index=entry_index,
        entry_time_ms=entry_time_ms,
        entry_price=entry_price,
    )
    if evaluation_start_offset not in (0, 1):
        raise InvalidRequestError("evaluation_start_offset must be 0 or 1")
    if target_index is None:
        target_index = len(frame.time_ms) - 1
    if target_index < entry_index or target_index >= len(frame.time_ms):
        raise InvalidRequestError("target_index is outside the managed replay frame")
    state.bars_in_trade = 1 if evaluation_start_offset == 1 else 0
    state.active_stop_price = initial_stop_price
    events: list[ManagedPolicyEvent] = []
    bars: list[ManagedBarDecision] = []
    evaluation_start_index = entry_index + evaluation_start_offset
    for index in range(evaluation_start_index, target_index + 1):
        bar = frame.market_bars[index]
        high, low, close = float(bar.high), float(bar.low), float(bar.close)
        _update_extremes(state, index=index, high=high, low=low)
        time_ms = frame.time_ms[index]
        for rule in phase_rules:
            to_phase = str(rule.get("to_phase", ""))
            if _rank(to_phase) <= _rank(state.phase):
                continue
            met, diagnostics = _phase_met(
                _mapping(rule.get("condition"), "phase rule condition"),
                state=state,
                index=index,
                frame=frame,
                plan=plan,
            )
            if not met:
                continue
            old = state.phase
            state.phase = to_phase
            if _rank(to_phase) > _rank(state.max_phase_reached):
                state.max_phase_reached = to_phase
            events.append(
                ManagedPolicyEvent(
                    time_ms,
                    index,
                    "phase_changed",
                    str(rule.get("rule_id", "")),
                    str(_mapping(rule.get("condition"), "condition").get("component_id", "")),
                    old,
                    to_phase,
                    state.mfe_price,
                    diagnostics,
                )
            )
        candidates: list[tuple[float, Mapping[str, Any]]] = []
        for rule in stop_rules:
            threshold = str(
                _mapping(rule.get("activate_when"), "activate_when").get("phase_at_least", "")
            )
            if not _at_least(state.phase, threshold):
                continue
            component_id = str(rule.get("component_id", ""))
            params = _mapping(rule.get("params", {}), "stop params")
            price: float | None = None
            if component_id == "break_even_stop":
                if params.get("buffer_type", "none") == "none":
                    buffer = float(params.get("buffer", 0.0))
                else:
                    atr_ref = _mapping(params.get("atr", {}), "break-even atr")
                    key = (
                        str(atr_ref.get("timeframe", "base")),
                        int(atr_ref.get("period", params.get("atr_period", 14))),
                    )
                    atr = _feature_value(frame, _atr_output_id(plan, key[0], key[1]), index)
                    if atr is None:
                        continue
                    buffer = float(params.get("buffer_atr", 0.0)) * atr
                price = state.entry_price + buffer if side == "long" else state.entry_price - buffer
            elif component_id == "lock_profit_stop":
                atr_ref = _mapping(params.get("atr", {}), "lock atr")
                key = (
                    str(atr_ref.get("timeframe", "base")),
                    int(atr_ref.get("period", params.get("atr_period", 14))),
                )
                atr = _feature_value(frame, _atr_output_id(plan, key[0], key[1]), index)
                if atr is None:
                    continue
                offset = float(params.get("lock_atr", 0.0)) * atr
                price = state.entry_price + offset if side == "long" else state.entry_price - offset
            else:
                raise InvalidRequestError(
                    "unsupported stop management component", component_id=component_id
                )
            candidates.append((price, rule))
        if candidates:
            chosen_price, chosen_rule = (
                max(candidates, key=lambda item: item[0])
                if side == "long"
                else min(candidates, key=lambda item: item[0])
            )
            tightened = (
                chosen_price
                if state.active_stop_price is None
                else max(state.active_stop_price, chosen_price)
                if side == "long"
                else min(state.active_stop_price, chosen_price)
            )
            if state.active_stop_price is None or abs(tightened - state.active_stop_price) > 1e-8:
                state.active_stop_price = tightened
                state.active_stop_rule_id = str(chosen_rule.get("rule_id", ""))
                state.active_stop_component_id = str(chosen_rule.get("component_id", ""))
                events.append(
                    ManagedPolicyEvent(
                        time_ms,
                        index,
                        "active_stop_updated",
                        state.active_stop_rule_id,
                        state.active_stop_component_id,
                        price=tightened,
                        metadata={"effective_from_bar": index + 1},
                    )
                )
        for rule in take_rules:
            threshold = str(
                _mapping(rule.get("activate_when"), "activate_when").get("phase_at_least", "")
            )
            if not _at_least(state.phase, threshold):
                continue
            if str(rule.get("component_id", "")) != "take_profile_switch":
                raise InvalidRequestError("unsupported take management component")
            action = str(_mapping(rule.get("params", {}), "take params").get("action", ""))
            profile = (
                "disable_initial_tp"
                if action == "disable_fixed_tp"
                else ("initial" if action == "keep_initial" else action)
            )
            if profile != state.active_take_profile:
                state.active_take_profile = profile
                state.active_take_rule_id = str(rule.get("rule_id", ""))
                state.active_take_component_id = "take_profile_switch"
                events.append(
                    ManagedPolicyEvent(
                        time_ms,
                        index,
                        "active_take_updated",
                        state.active_take_rule_id,
                        state.active_take_component_id,
                        metadata={"take_profile": profile, "effective_from_bar": index + 1},
                    )
                )
        armed: list[str] = []
        for rule in runtime_rules:
            threshold = str(
                _mapping(rule.get("activate_when"), "activate_when").get("phase_at_least", "")
            )
            if _at_least(state.phase, threshold) and _runtime_signal(
                rule,
                state=state,
                index=index,
                frame=frame,
                plan=plan,
                evaluation_start_index=evaluation_start_index,
            ):
                rule_id = str(rule.get("rule_id", ""))
                armed.append(rule_id)
                events.append(
                    ManagedPolicyEvent(
                        time_ms,
                        index,
                        "runtime_exit_triggered",
                        rule_id,
                        str(rule.get("component_id", "")),
                        price=close,
                        metadata={
                            "exit_kind": str(rule.get("exit_kind", "market_close")),
                            "effective_from_bar": index + 1,
                        },
                    )
                )
        state.active_runtime_exit_rules = tuple(armed)
        bars.append(
            ManagedBarDecision(
                time_ms,
                index,
                state.phase,
                state.bars_in_trade,
                state.mfe_pct,
                state.mae_pct,
                state.active_stop_price,
                state.active_take_profile,
                state.active_runtime_exit_rules,
                (frame.time_ms[index + 1] if index + 1 < len(frame.time_ms) else None),
            )
        )
    return ManagedReplayResult(trade_id, side, entry_time_ms, tuple(events), tuple(bars), state)


def evaluate_managed_replay(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    *,
    trade_id: str,
    side: Side,
    entry_time_ms: int,
    entry_price: float,
) -> ManagedReplayResult:
    """Preserve the public managed-replay entry-bar semantics."""

    return _evaluate_managed_replay_core(
        raw_spec,
        frame,
        plan,
        trade_id=trade_id,
        side=side,
        entry_time_ms=entry_time_ms,
        entry_price=entry_price,
        evaluation_start_offset=0,
        require_managed_mode=True,
    )


def evaluate_start_after_entry_managed_projection(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
    *,
    trade_id: str,
    side: Side,
    entry_time_ms: int,
    planned_entry_price: Decimal | float,
    initial_stop_price: Decimal | float,
    initial_take_price: Decimal | float,
    target_time_ms: int,
) -> StartAfterEntryManagedProjection:
    """Replay open-trade management strictly after entry using plan-price basis."""

    try:
        target_index = frame.time_ms.index(target_time_ms)
    except ValueError as exc:
        raise InvalidRequestError("target_time_ms is not on the evaluation grid") from exc
    planned_entry_decimal = (
        planned_entry_price
        if isinstance(planned_entry_price, Decimal)
        else Decimal(str(planned_entry_price))
    )
    initial_stop_decimal = (
        initial_stop_price
        if isinstance(initial_stop_price, Decimal)
        else Decimal(str(initial_stop_price))
    )
    initial_take_decimal = (
        initial_take_price
        if isinstance(initial_take_price, Decimal)
        else Decimal(str(initial_take_price))
    )
    if initial_stop_decimal <= 0 or initial_take_decimal <= 0:
        raise InvalidRequestError("initial stop and take prices must be positive")
    replay = _evaluate_managed_replay_core(
        raw_spec,
        frame,
        plan,
        trade_id=trade_id,
        side=side,
        entry_time_ms=entry_time_ms,
        entry_price=float(planned_entry_decimal),
        evaluation_start_offset=1,
        initial_stop_price=float(initial_stop_decimal),
        target_index=target_index,
        require_managed_mode=False,
    )
    desired_stop_price = (
        initial_stop_decimal
        if replay.final_state.active_stop_rule_id is None
        else Decimal(str(replay.final_state.active_stop_price))
    )
    desired_take_price = (
        None
        if replay.final_state.active_take_profile == "disable_initial_tp"
        else initial_take_decimal
    )
    return StartAfterEntryManagedProjection(
        replay=replay,
        desired_stop_price=desired_stop_price,
        desired_take_price=desired_take_price,
    )
