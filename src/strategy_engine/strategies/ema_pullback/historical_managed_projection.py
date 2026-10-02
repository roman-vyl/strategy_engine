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
from typing import TYPE_CHECKING, Literal

from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.strategies.contracts import (
    HistoricalManagedProjection,
    ManagedConditionSeries,
    ManagedPhaseTransitionRule,
    ManagedRule,
    ManagedRuntimeExitRule,
    ManagedStopActionRule,
    ManagedTakeActionRule,
    ManagedTransitionAtLeast,
    ManagedTransitionPath,
    ManagedTransitionTerm,
    ManagedTransitionThreshold,
    TradeMetric,
)
from strategy_engine.strategies.ema_pullback.composite_spec import COMPOSITE_PHASE_CONDITION
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.managed import (
    SeriesCache,
    _atr_output_id,
    _cached_series,
    _float,
    _initial_r_stop_params,
    _int,
    _items,
    _mapping,
)
from strategy_engine.strategies.ema_pullback.managed_composite import (
    ManagedPredicateIdentities,
    adx_di_series,
    fold_phase_paths,
    parse_if_composite,
)

if TYPE_CHECKING:
    from strategy_engine.indicators.evaluation_context import EvaluationContext
    from strategy_engine.strategies.ema_pullback.contexts import ContextBundle

_NAN = float("nan")


def _runtime_exit_class(
    exit_kind: str,
) -> Literal["runtime_protective", "runtime_take", "runtime_close"]:
    """Port of `research_service.execution.managed_policy._runtime_candidate_type` --
    kept in exact lockstep with that mapping (design.md D6a)."""

    if exit_kind == "protective_exit":
        return "runtime_protective"
    if exit_kind == "take_profit":
        return "runtime_take"
    return "runtime_close"


_METRIC: dict[str, TradeMetric] = {
    "mfe_atr": "mfe_distance",
    "mfe_pct": "mfe_pct",
    "mfe_r": "mfe_r",
    "bars_in_trade": "bars_since_entry",
}
_TRADE_ATOMS = frozenset(_METRIC)


def _trade_threshold(
    component_id: str,
    params: Mapping[str, object],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    cache: SeriesCache,
    bar_count: int,
) -> tuple[tuple[float, ...], TradeMetric]:
    """Per-bar threshold series and the trade metric it gates, for one
    trade atom -- shared by atomic rules and composite trade children."""

    if component_id == "mfe_atr":
        atr_threshold = _float(params.get("threshold"), "mfe_atr.threshold", positive=True)
        atr_ref = _mapping(params.get("atr"), "mfe_atr.atr")
        key = (
            str(atr_ref.get("timeframe", "")),
            _int(atr_ref.get("period"), "mfe_atr.atr.period"),
        )
        atr_values = _cached_series(cache, frame, _atr_output_id(plan, key[0], key[1]) or "")
        return (
            tuple(
                atr_threshold * atr if atr is not None and atr > 0 else _NAN for atr in atr_values
            ),
            _METRIC[component_id],
        )
    if component_id == "mfe_pct":
        pct_threshold = _float(params.get("threshold"), "mfe_pct.threshold", positive=True)
        return tuple(pct_threshold for _ in range(bar_count)), _METRIC[component_id]
    if component_id == "mfe_r":
        # mfe-r-phase-threshold-v1: the threshold is in R (multiples of the
        # trade's initial risk); the division by that trade's initial risk
        # is the executor's, so the series is constant.
        r_threshold = _float(params.get("threshold"), "mfe_r.threshold", positive=True)
        return tuple(r_threshold for _ in range(bar_count)), _METRIC[component_id]
    bars_threshold = _int(params.get("threshold"), "bars_in_trade.threshold")
    return tuple(float(bars_threshold) for _ in range(bar_count)), _METRIC[component_id]


def _composite_paths(
    rule_index: int,
    rule_id: str,
    condition: Mapping[str, object],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    cache: SeriesCache,
    bar_count: int,
    conditions: dict[str, ManagedConditionSeries],
    distances: dict[str, tuple[float, ...]],
    *,
    bundle: ContextBundle | None,
    context: EvaluationContext | None,
    identities: ManagedPredicateIdentities | None,
) -> tuple[ManagedTransitionPath, ...]:
    """The `paths` variant (design D6): one condition series per path for
    its folded market part, one distance per trade child, and the terms
    of an `at_least` that holds a trade child."""

    spec = parse_if_composite(condition, f"phase_rules[{rule_index}].condition")
    assert spec is not None
    by_side = {(index, side): children for index, side, children in identities or ()}
    folds = {
        side: fold_phase_paths(
            spec,
            frame,
            plan,
            side,
            bundle=bundle,
            context=context if (rule_index, side) in by_side else None,
            identities=by_side.get((rule_index, side)),
            series_cache=cache,
        )
        for side in ("long", "short")
    }
    long_fold, short_fold = folds["long"], folds["short"]

    def market_term(child_id: str) -> str:
        condition_id = f"phase:{rule_id}:child:{child_id}:condition"
        if condition_id not in conditions:
            conditions[condition_id] = ManagedConditionSeries(
                tuple(long_fold.market_children[child_id].tolist()),
                tuple(short_fold.market_children[child_id].tolist()),
            )
        return condition_id

    def trade_term(child_id: str) -> ManagedTransitionThreshold:
        # One distance per trade child, however many paths reference it.
        distance_id = f"phase:{rule_id}:child:{child_id}:distance"
        atom = spec.child(child_id).condition
        assert atom is not None
        component_id = str(atom.get("component_id", ""))
        if distance_id not in distances:
            distances[distance_id], _ = _trade_threshold(
                component_id,
                _mapping(atom.get("params", {}), "phase condition params"),
                frame,
                plan,
                cache,
                bar_count,
            )
        return ManagedTransitionThreshold(distance_id, _METRIC[component_id])

    paths: list[ManagedTransitionPath] = []
    for long_path, short_path in zip(long_fold.paths, short_fold.paths, strict=True):
        condition_id: str | None = None
        if long_path.market is not None:
            assert short_path.market is not None
            condition_id = f"phase:{rule_id}:path:{long_path.path_id}:condition"
            conditions[condition_id] = ManagedConditionSeries(
                tuple(long_path.market.tolist()), tuple(short_path.market.tolist())
            )
        at_least: ManagedTransitionAtLeast | None = None
        if long_path.at_least_k is not None:
            terms: list[ManagedTransitionTerm] = []
            for ref in long_path.at_least_terms:
                if ref in long_fold.market_children:
                    terms.append(ManagedTransitionTerm(market_term(ref), None, None))
                else:
                    threshold = trade_term(ref)
                    terms.append(
                        ManagedTransitionTerm(None, threshold.distance_id, threshold.trade_metric)
                    )
            at_least = ManagedTransitionAtLeast(long_path.at_least_k, tuple(terms))
        paths.append(
            ManagedTransitionPath(
                path_id=long_path.path_id,
                condition_id=condition_id,
                thresholds=tuple(trade_term(ref) for ref in long_path.trade_require),
                at_least=at_least,
            )
        )
    return tuple(paths)


def build_historical_managed_projection(
    raw_spec: Mapping[str, object],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    *,
    bundle: ContextBundle | None = None,
    context: EvaluationContext | None = None,
    identities: ManagedPredicateIdentities | None = None,
) -> HistoricalManagedProjection | None:
    """`None` unless `exit_management.mode == "managed"` -- matches
    `HistoricalManagedProjection`'s own "only present when managed"
    contract requirement. `bundle`, `context` and `identities` serve only
    composite phase conditions: the HTF state of `state` predicates, and
    memoized predicate children (design D7, D8)."""

    management = _mapping(raw_spec.get("trade_management", {}), "trade_management")
    config = _mapping(management.get("exit_management", {}), "exit_management")
    if config.get("mode") != "managed":
        return None

    bar_count = len(frame.time_ms)
    cache: SeriesCache = {}
    conditions: dict[str, ManagedConditionSeries] = {}
    distances: dict[str, tuple[float, ...]] = {}
    rules: list[ManagedRule] = []

    for rule_index, phase_rule in enumerate(_items(config.get("phase_rules", ()), "phase_rules")):
        rule_id = str(phase_rule.get("rule_id", ""))
        target_phase = str(phase_rule.get("to_phase", ""))
        condition = _mapping(phase_rule.get("condition"), f"phase_rules[{rule_id}].condition")
        component_id = str(condition.get("component_id", ""))
        params = _mapping(condition.get("params", {}), "phase condition params")

        if component_id == COMPOSITE_PHASE_CONDITION:
            rules.append(
                ManagedPhaseTransitionRule(
                    kind="phase_transition",
                    rule_id=rule_id,
                    target_phase=target_phase,
                    condition_id=None,
                    distance_id=None,
                    trade_metric=None,
                    paths=_composite_paths(
                        rule_index,
                        rule_id,
                        condition,
                        frame,
                        plan,
                        cache,
                        bar_count,
                        conditions,
                        distances,
                        bundle=bundle,
                        context=context,
                        identities=identities,
                    ),
                )
            )
            continue

        if component_id == "adx_di_threshold":
            long_series, short_series = adx_di_series(params, frame, plan, cache)
            condition_id = f"phase:{rule_id}:condition"
            conditions[condition_id] = ManagedConditionSeries(long_series, short_series)
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

        if component_id in _TRADE_ATOMS:
            distance_id = f"phase:{rule_id}:distance"
            distances[distance_id], trade_metric = _trade_threshold(
                component_id, params, frame, plan, cache, bar_count
            )
            rules.append(
                ManagedPhaseTransitionRule(
                    kind="phase_transition",
                    rule_id=rule_id,
                    target_phase=target_phase,
                    condition_id=None,
                    distance_id=distance_id,
                    trade_metric=trade_metric,
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
        stop_formula = None
        trigger_distance_id = None

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
                atr_values = _cached_series(
                    cache, frame, _atr_output_id(plan, key[0], key[1]) or ""
                )
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
            initial_r = _initial_r_stop_params(component_id, params)
            if initial_r is None:
                raise ValueError(f"unsupported stop management component_id={component_id!r}")
            stop_formula, trigger_r, action_r = initial_r
            trigger_distance_id = f"stop:{rule_id}:trigger"
            distances[trigger_distance_id] = tuple(trigger_r for _ in range(bar_count))
            distances[distance_id] = tuple(action_r for _ in range(bar_count))

        rules.append(
            ManagedStopActionRule(
                kind="stop_action",
                rule_id=rule_id,
                activation_phase=activation_phase,
                distance_id=distance_id,
                stop_formula=stop_formula,
                trigger_distance_id=trigger_distance_id,
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
            output_id = plan.rsi_columns.get(
                (str(rsi_ref.get("timeframe", "")), int(rsi_ref.get("period", 0)))
            )
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
            fast_id = plan.ema_columns.get(
                (str(fast_ref.get("timeframe", "")), int(fast_ref.get("period", 0)))
            )
            slow_id = plan.ema_columns.get(
                (str(slow_ref.get("timeframe", "")), int(slow_ref.get("period", 0)))
            )
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

    return HistoricalManagedProjection(
        conditions=conditions, distances=distances, rules=tuple(rules)
    )
