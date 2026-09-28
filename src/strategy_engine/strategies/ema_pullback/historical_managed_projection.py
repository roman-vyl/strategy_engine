"""Candidate-wide managed-policy projection (`historical-managed-projection-v1`).

Computed at most once per candidate, over the candidate's full requested
range, from the exact same formulas `managed.py`'s single-trade replay
uses. Deliberately reuses `managed.py`'s own parsing/formula helpers
(`_mapping`, `_items`, `_int`, `_float`, `_atr_output_id`, `_series`,
`_cached_series`) rather than duplicating them, so this evaluator and the
single-trade replay it must stay parity-equivalent with can never drift
on those primitives. Does NOT reuse `exits.py`'s `_signal_rule`/
`_distance` -- proven not semantically identical (design.md D5).

Convention: a `distances` entry is `float('nan')` at any bar where the
underlying formula is not evaluable (missing indicator value, or an ATR
reading `managed.py` itself would reject) -- `NaN` compares False against
everything, so a consumer's `>=` comparison naturally reproduces
`managed.py`'s "not ready -> condition not met" / "not ready -> no stop
candidate this bar" behavior without any special-casing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.managed import (
    SeriesCache,
    _atr_output_id,
    _cached_series,
    _float,
    _int,
    _items,
    _mapping,
)
from strategy_engine.strategies.contracts import (
    HistoricalManagedProjection,
    ManagedConditionSeries,
    ManagedPhaseTransitionRule,
    ManagedRule,
    ManagedRuntimeExitRule,
    ManagedStopActionRule,
    ManagedTakeActionRule,
)

_NAN = float("nan")


def _runtime_exit_class(exit_kind: str) -> Literal["runtime_protective", "runtime_take", "runtime_close"]:
    """Port of `research_service.execution.managed_policy._runtime_candidate_type` --
    kept in exact lockstep with that mapping (design.md D6a)."""

    if exit_kind == "protective_exit":
        return "runtime_protective"
    if exit_kind == "take_profit":
        return "runtime_take"
    return "runtime_close"


def build_historical_managed_projection(
    raw_spec: Mapping[str, object],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
) -> HistoricalManagedProjection | None:
    """`None` unless `exit_management.mode == "managed"` -- matches
    `HistoricalManagedProjection`'s own "only present when managed"
    contract requirement."""

    management = _mapping(raw_spec.get("trade_management", {}), "trade_management")
    config = _mapping(management.get("exit_management", {}), "exit_management")
    if config.get("mode") != "managed":
        return None

    bar_count = len(frame.time_ms)
    cache: SeriesCache = {}
    conditions: dict[str, ManagedConditionSeries] = {}
    distances: dict[str, tuple[float, ...]] = {}
    rules: list[ManagedRule] = []

    for phase_rule in _items(config.get("phase_rules", ()), "phase_rules"):
        rule_id = str(phase_rule.get("rule_id", ""))
        target_phase = str(phase_rule.get("to_phase", ""))
        condition = _mapping(phase_rule.get("condition"), f"phase_rules[{rule_id}].condition")
        component_id = str(condition.get("component_id", ""))
        params = _mapping(condition.get("params", {}), "phase condition params")

        if component_id == "adx_di_threshold":
            key = (str(params.get("timeframe", "")), _int(params.get("period"), "adx_di_threshold.period"))
            columns = plan.adx_dmi_columns.get(key, {})
            adx_values = _cached_series(cache, frame, columns.get("adx", ""))
            plus_values = _cached_series(cache, frame, columns.get("di_plus", ""))
            minus_values = _cached_series(cache, frame, columns.get("di_minus", ""))
            adx_threshold = _float(params.get("adx_threshold"), "adx_di_threshold.adx_threshold", positive=True)
            require = params.get("require_di_alignment", True)
            long_series: list[bool] = []
            short_series: list[bool] = []
            for adx, plus, minus in zip(adx_values, plus_values, minus_values, strict=True):
                if adx is None or plus is None or minus is None:
                    long_series.append(False)
                    short_series.append(False)
                    continue
                ok = adx >= adx_threshold
                long_series.append(ok and (not require or plus > minus))
                short_series.append(ok and (not require or minus > plus))
            condition_id = f"phase:{rule_id}:condition"
            conditions[condition_id] = ManagedConditionSeries(tuple(long_series), tuple(short_series))
            rules.append(
                ManagedPhaseTransitionRule(
                    kind="phase_transition",
                    rule_id=rule_id,
                    target_phase=target_phase,
                    condition_id=condition_id,
                    distance_id=None,
                    trade_metric=None,
                )
            )
            continue

        if component_id == "mfe_atr":
            atr_threshold = _float(params.get("threshold"), "mfe_atr.threshold", positive=True)
            atr_ref = _mapping(params.get("atr"), "mfe_atr.atr")
            key = (str(atr_ref.get("timeframe", "")), _int(atr_ref.get("period"), "mfe_atr.atr.period"))
            atr_values = _cached_series(cache, frame, _atr_output_id(plan, key[0], key[1]) or "")
            distance_id = f"phase:{rule_id}:distance"
            distances[distance_id] = tuple(
                atr_threshold * atr if atr is not None and atr > 0 else _NAN for atr in atr_values
            )
            rules.append(
                ManagedPhaseTransitionRule(
                    kind="phase_transition",
                    rule_id=rule_id,
                    target_phase=target_phase,
                    condition_id=None,
                    distance_id=distance_id,
                    trade_metric="mfe_distance",
                )
            )
            continue

        if component_id == "mfe_pct":
            pct_threshold = _float(params.get("threshold"), "mfe_pct.threshold", positive=True)
            distance_id = f"phase:{rule_id}:distance"
            distances[distance_id] = tuple(pct_threshold for _ in range(bar_count))
            rules.append(
                ManagedPhaseTransitionRule(
                    kind="phase_transition",
                    rule_id=rule_id,
                    target_phase=target_phase,
                    condition_id=None,
                    distance_id=distance_id,
                    trade_metric="mfe_pct",
                )
            )
            continue

        if component_id == "bars_in_trade":
            bars_threshold = _int(params.get("threshold"), "bars_in_trade.threshold")
            distance_id = f"phase:{rule_id}:distance"
            distances[distance_id] = tuple(float(bars_threshold) for _ in range(bar_count))
            rules.append(
                ManagedPhaseTransitionRule(
                    kind="phase_transition",
                    rule_id=rule_id,
                    target_phase=target_phase,
                    condition_id=None,
                    distance_id=distance_id,
                    trade_metric="bars_since_entry",
                )
            )
            continue

        raise ValueError(f"unsupported phase condition component_id={component_id!r}")

    for stop_rule in _items(config.get("stop_management", ()), "stop_management"):
        rule_id = str(stop_rule.get("rule_id", ""))
        activation_phase = str(
            _mapping(stop_rule.get("activate_when"), "activate_when").get("phase_at_least", "")
        )
        component_id = str(stop_rule.get("component_id", ""))
        params = _mapping(stop_rule.get("params", {}), "stop params")
        distance_id = f"stop:{rule_id}:distance"

        if component_id == "break_even_stop":
            if params.get("buffer_type", "none") == "none":
                buffer = float(params.get("buffer", 0.0))
                distances[distance_id] = tuple(buffer for _ in range(bar_count))
            else:
                atr_ref = _mapping(params.get("atr", {}), "break-even atr")
                key = (
                    str(atr_ref.get("timeframe", "base")),
                    int(atr_ref.get("period", params.get("atr_period", 14))),
                )
                atr_values = _cached_series(cache, frame, _atr_output_id(plan, key[0], key[1]) or "")
                buffer_atr = float(params.get("buffer_atr", 0.0))
                distances[distance_id] = tuple(
                    buffer_atr * atr if atr is not None else _NAN for atr in atr_values
                )
        elif component_id == "lock_profit_stop":
            atr_ref = _mapping(params.get("atr", {}), "lock atr")
            key = (
                str(atr_ref.get("timeframe", "base")),
                int(atr_ref.get("period", params.get("atr_period", 14))),
            )
            atr_values = _cached_series(cache, frame, _atr_output_id(plan, key[0], key[1]) or "")
            lock_atr = float(params.get("lock_atr", 0.0))
            distances[distance_id] = tuple(
                lock_atr * atr if atr is not None else _NAN for atr in atr_values
            )
        else:
            raise ValueError(f"unsupported stop management component_id={component_id!r}")

        rules.append(
            ManagedStopActionRule(
                kind="stop_action",
                rule_id=rule_id,
                activation_phase=activation_phase,
                distance_id=distance_id,
            )
        )

    for take_rule in _items(config.get("take_management", ()), "take_management"):
        rule_id = str(take_rule.get("rule_id", ""))
        activation_phase = str(
            _mapping(take_rule.get("activate_when"), "activate_when").get("phase_at_least", "")
        )
        if str(take_rule.get("component_id", "")) != "take_profile_switch":
            raise ValueError("unsupported take management component")
        action = str(_mapping(take_rule.get("params", {}), "take params").get("action", ""))
        resulting_profile = (
            "disable_initial_tp"
            if action == "disable_fixed_tp"
            else ("initial" if action == "keep_initial" else action)
        )
        rules.append(
            ManagedTakeActionRule(
                kind="take_action",
                rule_id=rule_id,
                activation_phase=activation_phase,
                resulting_profile=resulting_profile,
            )
        )

    for runtime_rule in _items(config.get("runtime_exits", ()), "runtime_exits"):
        rule_id = str(runtime_rule.get("rule_id", ""))
        activation_phase = str(
            _mapping(runtime_rule.get("activate_when"), "activate_when").get("phase_at_least", "")
        )
        component_id = str(runtime_rule.get("component_id", ""))
        params = _mapping(runtime_rule.get("params", {}), "runtime exit params")
        confirm_bars = _int(params.get("confirm_bars", 1), "confirm_bars")
        exit_kind = str(runtime_rule.get("exit_kind", "market_close"))
        exit_class = _runtime_exit_class(exit_kind)
        condition_id = f"runtime:{rule_id}:condition"

        if component_id == "phase_runtime_exit":
            is_close = str(params.get("exit_price", "close")) == "close"
            conditions[condition_id] = ManagedConditionSeries(
                tuple(is_close for _ in range(bar_count)), tuple(is_close for _ in range(bar_count))
            )
        elif component_id == "rsi_signal_exit":
            rsi_ref = _mapping(params.get("rsi"), "runtime rsi")
            output_id = plan.rsi_columns.get((str(rsi_ref.get("timeframe", "")), int(rsi_ref.get("period", 0))))
            values = _cached_series(cache, frame, output_id or "")
            long_threshold = params.get("long_exit_above")
            short_threshold = params.get("short_exit_below")
            long_boundary = None if long_threshold is None else float(long_threshold)
            short_boundary = None if short_threshold is None else float(short_threshold)
            conditions[condition_id] = ManagedConditionSeries(
                tuple(
                    (long_boundary is not None and value is not None and value >= long_boundary)
                    for value in values
                ),
                tuple(
                    (short_boundary is not None and value is not None and value <= short_boundary)
                    for value in values
                ),
            )
        elif component_id == "ema_cross_loss_exit":
            fast_ref = _mapping(params.get("fast_ema"), "runtime fast_ema")
            slow_ref = _mapping(params.get("slow_ema"), "runtime slow_ema")
            fast_id = plan.ema_columns.get((str(fast_ref.get("timeframe", "")), int(fast_ref.get("period", 0))))
            slow_id = plan.ema_columns.get((str(slow_ref.get("timeframe", "")), int(slow_ref.get("period", 0))))
            fast_values = _cached_series(cache, frame, fast_id or "")
            slow_values = _cached_series(cache, frame, slow_id or "")
            conditions[condition_id] = ManagedConditionSeries(
                tuple(
                    (fast is not None and slow is not None and fast <= slow)
                    for fast, slow in zip(fast_values, slow_values, strict=True)
                ),
                tuple(
                    (fast is not None and slow is not None and fast >= slow)
                    for fast, slow in zip(fast_values, slow_values, strict=True)
                ),
            )
        else:
            raise ValueError(f"unsupported runtime exit component_id={component_id!r}")

        rules.append(
            ManagedRuntimeExitRule(
                kind="runtime_exit",
                rule_id=rule_id,
                activation_phase=activation_phase,
                condition_id=condition_id,
                confirm_bars=confirm_bars,
                exit_class=exit_class,
            )
        )

    return HistoricalManagedProjection(conditions=conditions, distances=distances, rules=tuple(rules))
