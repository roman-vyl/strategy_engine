"""Semantic-parity corpus (`historical-managed-projection-v1` acceptance
criterion 1, managed-policy layer only -- see specs/historical-managed-
projection-v1/spec.md's "Managed-policy parity" requirement).

`_replay_from_projection` below is a minimal, strategy-agnostic reference
consumer -- it plays the same role Research Service's real generic managed
lifecycle primitives (tasks.md section 4) will play, built here so the
Strategy Engine-side projection can be parity-tested against
`evaluate_managed_replay` before any Research Service code depends on it
(tasks.md 3.2/3.3 gate). It reads ONLY `HistoricalManagedProjection` plus
locally-owned trade state (entry price/index/side, running MFE, bars since
entry) -- never `component_id`, never a raw strategy parameter -- exactly
as the spec's "Research dispatches on rule kind alone" scenario requires.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.contracts import (
    HistoricalManagedProjection,
    ManagedTransitionEntryChange,
    ManagedTransitionPath,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.historical_managed_projection import (
    build_historical_managed_projection,
)
from strategy_engine.strategies.ema_pullback.managed import _PHASES, evaluate_managed_replay

_RANK = {name: index for index, name in enumerate(_PHASES)}


def _at_least(current: str, threshold: str) -> bool:
    if not threshold:
        return True
    return _RANK[current] >= _RANK[threshold]


def _threshold_met(
    projection: HistoricalManagedProjection,
    distance_id: str,
    trade_metric: str,
    values: dict[str, float],
    index: int,
) -> bool:
    return values[trade_metric] >= projection.distances[distance_id][index]


_ENTRY_CHANGE_OPS = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
}


def _entry_change_met(
    projection: HistoricalManagedProjection,
    change: ManagedTransitionEntryChange,
    entry_index: int,
    index: int,
    fault: str | None,
) -> bool:
    """`entry-anchored-change-v1` design D7: `series[i] - series[entry]
    <op> value`, NaN -> False."""

    series = projection.distances[change.series_id]
    anchor = series[entry_index - 1 if fault == "anchor_one_bar_early" else entry_index]
    current = series[index]
    if not (math.isfinite(anchor) and math.isfinite(current)):
        return False
    return bool(_ENTRY_CHANGE_OPS[change.op](current - anchor, change.value))


def _path_met(
    projection: HistoricalManagedProjection,
    path: ManagedTransitionPath,
    side: str,
    values: dict[str, float],
    index: int,
    fault: str | None,
    entry_index: int = 0,
) -> bool:
    """The `paths` rule of `composite-managed-phase-condition-v1` design D6.
    `fault` injects one deliberate consumer bug (task 6.2 controls)."""

    def condition(condition_id: str) -> bool:
        series = projection.conditions[condition_id]
        return (series.long if side == "long" else series.short)[index]

    if path.condition_id is not None and not condition(path.condition_id):
        return False
    if fault != "ignore_thresholds" and not all(
        _threshold_met(projection, t.distance_id, t.trade_metric, values, index)
        for t in path.thresholds
    ):
        return False
    if fault != "ignore_entry_changes" and not all(
        _entry_change_met(projection, change, entry_index, index, fault)
        for change in path.entry_changes
    ):
        return False
    at_least = path.at_least
    if at_least is None:
        return True
    market_terms = [t for t in at_least.terms if t.condition_id is not None]
    trade_terms = [t for t in at_least.terms if t.condition_id is None]
    if fault == "drop_trade_only_at_least" and not market_terms:
        return True
    if fault == "ignore_mixed_trade_terms" and market_terms:
        trade_terms = []
    count = sum(condition(t.condition_id) for t in market_terms if t.condition_id is not None)
    for term in trade_terms:
        if term.entry_change is not None:
            count += _entry_change_met(projection, term.entry_change, entry_index, index, fault)
            continue
        assert term.distance_id is not None and term.trade_metric is not None
        count += _threshold_met(projection, term.distance_id, term.trade_metric, values, index)
    return count >= at_least.k


def _replay_from_projection(
    projection: HistoricalManagedProjection,
    market_bars: tuple[MarketBar, ...],
    *,
    side: str,
    entry_index: int,
    entry_price: float,
    target_index: int,
    start_offset: int = 0,
    initial_stop_price: float | None = None,
    transitions: list[tuple[int, str, str | None]] | None = None,
    fault: str | None = None,
) -> list[tuple[str, float | None, str, tuple[str, ...]]]:
    """`transitions` (optional out): every phase transition as (bar,
    rule_id, path_id). `start_offset` 1 is the live start-after-entry
    variant."""

    phase_rules = [r for r in projection.rules if r.kind == "phase_transition"]
    stop_rules = [r for r in projection.rules if r.kind == "stop_action"]
    take_rules = [r for r in projection.rules if r.kind == "take_action"]
    runtime_rules = [r for r in projection.rules if r.kind == "runtime_exit"]

    phase = "initial_risk"
    active_stop_price = initial_stop_price
    active_take_profile = "initial"
    best_price = entry_price
    out: list[tuple[str, float | None, str, tuple[str, ...]]] = []

    for index in range(entry_index + start_offset, target_index + 1):
        bar = market_bars[index]
        high, low = float(bar.high), float(bar.low)
        if side == "long":
            best_price = max(best_price, high)
            mfe_price = best_price
            mfe_pct = (best_price - entry_price) / entry_price
        else:
            best_price = min(best_price, low)
            mfe_price = best_price
            mfe_pct = (entry_price - best_price) / entry_price
        bars_in_trade = index - entry_index + 1
        mfe_distance = abs(mfe_price - entry_price)
        trade_metric_values = {
            "bars_since_entry": float(bars_in_trade),
            "mfe_pct": mfe_pct,
            "mfe_distance": mfe_distance,
            "mfe_r": (
                float("nan")
                if initial_stop_price is None
                or abs(entry_price - initial_stop_price) <= 0
                else mfe_distance / abs(entry_price - initial_stop_price)
            ),
        }

        for rule in phase_rules:
            if _RANK[rule.target_phase] <= _RANK[phase]:
                continue
            path_id: str | None = None
            if rule.paths is not None:
                path_id = next(
                    (
                        path.path_id
                        for path in rule.paths
                        if _path_met(
                            projection, path, side, trade_metric_values, index, fault, entry_index
                        )
                    ),
                    None,
                )
                met = path_id is not None
            elif rule.condition_id is not None:
                series = projection.conditions[rule.condition_id]
                met = (series.long if side == "long" else series.short)[index]
            else:
                assert rule.distance_id is not None and rule.trade_metric is not None
                threshold = projection.distances[rule.distance_id][index]
                met = trade_metric_values[rule.trade_metric] >= threshold
            if met:
                phase = rule.target_phase
                if transitions is not None:
                    transitions.append((index, rule.rule_id, path_id))

        candidates: list[float] = []
        for rule in stop_rules:
            if not _at_least(phase, rule.activation_phase):
                continue
            distance = projection.distances[rule.distance_id][index]
            if distance != distance:  # NaN: "not ready this bar", per contract convention
                continue
            if rule.stop_formula is None:
                price = entry_price + distance if side == "long" else entry_price - distance
            else:
                assert rule.trigger_distance_id is not None
                trigger = projection.distances[rule.trigger_distance_id][index]
                initial_risk = (
                    None
                    if initial_stop_price is None
                    else abs(entry_price - initial_stop_price)
                )
                if (
                    initial_risk is None
                    or initial_risk <= 0
                    or trade_metric_values["mfe_r"] < trigger
                ):
                    continue
                offset = distance * initial_risk
                if rule.stop_formula == "initial_r_lock":
                    price = entry_price + offset if side == "long" else entry_price - offset
                else:
                    price = mfe_price - offset if side == "long" else mfe_price + offset
            candidates.append(price)
        if candidates:
            chosen = max(candidates) if side == "long" else min(candidates)
            active_stop_price = (
                chosen
                if active_stop_price is None
                else (
                    max(active_stop_price, chosen)
                    if side == "long"
                    else min(active_stop_price, chosen)
                )
            )

        for rule in take_rules:
            if not _at_least(phase, rule.activation_phase):
                continue
            active_take_profile = rule.resulting_profile

        armed: list[str] = []
        for rule in runtime_rules:
            if not _at_least(phase, rule.activation_phase):
                continue
            series = projection.conditions[rule.condition_id]
            values = series.long if side == "long" else series.short
            start = index - rule.confirm_bars + 1
            if start < entry_index:
                continue
            if all(values[pos] for pos in range(start, index + 1)):
                armed.append(rule.rule_id)

        out.append((phase, active_stop_price, active_take_profile, tuple(armed)))
    return out


def _spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "trade_sides": {"enabled": ["long", "short"]},
        "components": {"blockers": [], "trigger": {"component_id": "touch_anchor"}},
        "setups": [],
        "contexts": {},
        "trade_management": {
            "exit_policy": {
                "always_on": {"exits": []},
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {
                "mode": "managed",
                "phase_rules": [
                    {
                        "rule_id": "to-proven",
                        "to_phase": "proven",
                        "condition": {
                            "component_id": "adx_di_threshold",
                            "params": {
                                "timeframe": "base",
                                "period": 3,
                                "adx_threshold": 1.0,
                                "require_di_alignment": False,
                            },
                        },
                    },
                    {
                        "rule_id": "to-protected",
                        "to_phase": "protected",
                        "condition": {
                            "component_id": "bars_in_trade",
                            "params": {"threshold": 2},
                        },
                    },
                    {
                        "rule_id": "to-runner",
                        "to_phase": "runner",
                        "condition": {
                            "component_id": "mfe_pct",
                            "params": {"threshold": 0.01},
                        },
                    },
                    {
                        "rule_id": "to-exhaustion",
                        "to_phase": "exhaustion",
                        "condition": {
                            "component_id": "mfe_atr",
                            "params": {
                                "threshold": 0.5,
                                "atr": {"timeframe": "base", "period": 2},
                            },
                        },
                    },
                ],
                "stop_management": [
                    {
                        "rule_id": "be",
                        "component_id": "break_even_stop",
                        "activate_when": {"phase_at_least": "protected"},
                        "params": {"buffer_type": "none", "buffer": 0.25},
                    },
                    {
                        "rule_id": "lock",
                        "component_id": "lock_profit_stop",
                        "activate_when": {"phase_at_least": "runner"},
                        "params": {"lock_atr": 0.5, "atr_period": 2},
                    },
                ],
                "take_management": [
                    {
                        "rule_id": "disable-tp",
                        "component_id": "take_profile_switch",
                        "activate_when": {"phase_at_least": "runner"},
                        "params": {"action": "disable_fixed_tp"},
                    }
                ],
                "runtime_exits": [
                    {
                        "rule_id": "close-exhaustion",
                        "component_id": "phase_runtime_exit",
                        "activate_when": {"phase_at_least": "exhaustion"},
                        "exit_kind": "market_close",
                        "params": {"exit_price": "close"},
                    },
                    {
                        "rule_id": "rsi-exit",
                        "component_id": "rsi_signal_exit",
                        "activate_when": {"phase_at_least": "initial_risk"},
                        "exit_kind": "signal",
                        "params": {
                            "confirm_bars": 2,
                            "rsi": {"timeframe": "base", "period": 2},
                            "long_exit_above": 40.0,
                            "short_exit_below": 60.0,
                        },
                    },
                    {
                        "rule_id": "ema-cross",
                        "component_id": "ema_cross_loss_exit",
                        "activate_when": {"phase_at_least": "initial_risk"},
                        "exit_kind": "protective_exit",
                        "params": {
                            "confirm_bars": 1,
                            "fast_ema": {"source": "close", "timeframe": "base", "period": 2},
                            "slow_ema": {"source": "close", "timeframe": "base", "period": 3},
                        },
                    },
                ],
            },
        },
    }


def _frame(raw: dict[str, object], n: int = 10) -> tuple[FeatureFrame, object]:
    plan = build_feature_plan_from_canonical_spec(raw)
    times = tuple(i * 300_000 for i in range(n))
    closes = [100, 99, 101, 104, 103, 108, 106, 112, 109, 120][:n]
    bars = tuple(
        MarketBar(
            times[i],
            Decimal(str(closes[i] - 1)),
            Decimal(str(closes[i] + 2)),
            Decimal(str(closes[i] - 2)),
            Decimal(str(closes[i])),
            Decimal("1"),
        )
        for i in range(n)
    )

    def series_for(kind: str, timeframe: str, period: int) -> tuple[str | None, ...]:
        source = [Decimal(str(closes[i])) for i in range(n)]
        if kind == "atr":
            return tuple("2" for _ in range(n))
        if kind == "rsi":
            # Deterministic pseudo-RSI walk so both long/short confirm windows exercise.
            values = [
                50 + (10 if closes[i] > closes[i - 1] else -10) if i > 0 else 50 for i in range(n)
            ]
            return tuple(str(v) for v in values)
        if kind == "ema":
            return tuple(str(source[i]) for i in range(n))
        if kind in ("adx", "di_plus", "di_minus"):
            if kind == "adx":
                return tuple("30" for _ in range(n))
            if kind == "di_plus":
                return tuple(
                    ("25" if closes[i] >= closes[i - 1] else "10") if i > 0 else "25"
                    for i in range(n)
                )
            return tuple(
                ("10" if closes[i] >= closes[i - 1] else "25") if i > 0 else "10" for i in range(n)
            )
        raise AssertionError(kind)

    series: dict[str, tuple[str | None, ...]] = {}
    for feature in plan.indicator_plan.features:
        series[feature.output_id] = series_for(
            feature.kind, feature.timeframe, feature.parameters.get("period", 0)
        )

    return (
        FeatureFrame(
            MarketStream("BTCUSDT.P", "5m"),
            TimeRange(0, times[-1]),
            times,
            series,
            {},
            "plan",
            "market",
            bars,
        ),
        plan,
    )


@pytest.mark.parametrize(
    ("side", "entry_index"),
    [("long", 0), ("long", 3), ("short", 0), ("short", 2)],
)
def test_projection_matches_managed_replay_bar_for_bar(side: str, entry_index: int) -> None:
    raw = _spec()
    feature_frame, plan = _frame(raw)
    entry_price = float(feature_frame.market_bars[entry_index].close)
    target_index = len(feature_frame.time_ms) - 1

    oracle = evaluate_managed_replay(
        raw,
        feature_frame,
        plan,
        trade_id="T",
        side=side,  # type: ignore[arg-type]
        entry_time_ms=feature_frame.time_ms[entry_index],
        entry_price=entry_price,
    )
    oracle_bars = [
        (bar.phase, bar.active_stop_price, bar.active_take_profile, bar.runtime_exit_rule_ids)
        for bar in oracle.bars
    ]

    projection = build_historical_managed_projection(raw, feature_frame, plan)
    assert projection is not None
    projected_bars = _replay_from_projection(
        projection,
        feature_frame.market_bars,
        side=side,
        entry_index=entry_index,
        entry_price=entry_price,
        target_index=target_index,
    )

    assert len(projected_bars) == len(oracle_bars)
    for i, (projected, expected) in enumerate(zip(projected_bars, oracle_bars, strict=True)):
        assert projected[0] == expected[0], f"bar {i}: phase {projected[0]!r} != {expected[0]!r}"
        if expected[1] is None:
            assert projected[1] is None, f"bar {i}: stop {projected[1]!r} != None"
        else:
            assert projected[1] is not None and abs(projected[1] - expected[1]) < 1e-9, (
                f"bar {i}: stop {projected[1]!r} != {expected[1]!r}"
            )
        assert projected[2] == expected[2], (
            f"bar {i}: take_profile {projected[2]!r} != {expected[2]!r}"
        )
        assert set(projected[3]) == set(expected[3]), (
            f"bar {i}: runtime_exits {projected[3]!r} != {expected[3]!r}"
        )


def test_non_managed_spec_produces_no_projection() -> None:
    raw = _spec()
    exit_management = raw["trade_management"]["exit_management"]  # type: ignore[index]
    exit_management["mode"] = "static"  # type: ignore[index]
    feature_frame, plan = _frame(raw)
    assert build_historical_managed_projection(raw, feature_frame, plan) is None


def test_rules_are_generic_discriminated_union_only() -> None:
    """Guards the spec's "Research dispatches on rule kind alone" scenario:
    every rule is one of exactly the four documented kinds, and each
    variant carries only opaque/generic fields -- never a component_id."""

    raw = _spec()
    feature_frame, plan = _frame(raw)
    projection = build_historical_managed_projection(raw, feature_frame, plan)
    assert projection is not None
    kinds = {rule.kind for rule in projection.rules}
    assert kinds == {"phase_transition", "take_action", "stop_action", "runtime_exit"}
    for rule in projection.rules:
        assert not hasattr(rule, "component_id")


# -- composite phase conditions (composite-managed-phase-condition-v1, 6.1/6.2) --
#
# On the parity market fixture: for every corpus spec, side and entry, the
# reference consumer's (bar, rule_id, path_id) transitions and per-bar
# decisions equal `evaluate_managed_replay` (offset 0) and the live
# start-after-entry replay (offset 1).


def _composite_corpus() -> dict[str, dict[str, object]]:
    from parity.composite_phase_corpus import (
        ADX1H,
        ADX5,
        BARS,
        DI1H,
        MFE_PCT,
        _composite,
        _cond,
        _pred,
        _spec,
        entry_change_at_least,
        entry_change_case,
        mixed_at_least,
        owner_case,
        state_temporal,
        trade_only_at_least,
    )
    from parity.managed_invariants import _exit_management

    market_at_least = _composite(
        [_pred("adx5", ADX5), _pred("adx1h", ADX1H), _pred("di1h", DI1H)],
        [{"path_id": "vote", "at_least": {"k": 2, "of": ["adx5", "adx1h", "di1h"]}}],
    )
    trade_path = _composite(
        [_cond("bars", BARS), _cond("pct", MFE_PCT), _pred("adx1h", ADX1H)],
        [
            {"path_id": "trade", "require": ["bars", "pct"]},
            {"path_id": "market", "require": ["adx1h"]},
        ],
    )
    cascade = _spec(
        owner_case(),
        trade_only_at_least(),
        state_temporal(),
        to_phases=("proven", "protected", "runner"),
    )
    actions = _exit_management(
        proven_tf="1h",
        adx_threshold=20.0,
        require_di=True,
        protected_mfe_atr=2.0,
        runner_mfe_pct=0.01,
    )
    exit_management = cascade["trade_management"]["exit_management"]  # type: ignore[index]
    for key in ("stop_management", "take_management", "runtime_exits"):
        exit_management[key] = actions[key]  # type: ignore[index]
    return {
        "owner_case": _spec(owner_case()),
        "mixed_at_least": _spec(mixed_at_least()),
        "market_at_least": _spec(market_at_least),
        "trade_only_at_least": _spec(trade_only_at_least()),
        "trade_only_path": _spec(trade_path),
        "state_temporal": _spec(state_temporal()),
        "cascade_with_actions": cascade,
        "entry_change": _spec(entry_change_case()),
        "entry_change_at_least": _spec(entry_change_at_least()),
    }


_CORPUS_ENTRIES = tuple(range(150, 11_900, 397))
# (spec, side, entry) -> oracle result; the corpus is deterministic and
# module-scoped, so the oracle replays once for all corpus tests.
_ORACLE_CACHE: dict[
    tuple[str, str, int],
    tuple[list[tuple[int, str, str | None]], list[tuple[str, float | None, str, tuple[str, ...]]]],
] = {}


@pytest.fixture(scope="module")
def composite_corpus() -> dict[str, tuple[dict[str, object], object, object, object, object]]:
    """spec name -> (raw spec, full-fixture frame, plan, context bundle,
    projection)."""

    from parity.harness import market_fixture_meta
    from parity.managed_invariants import _slice_services

    from strategy_engine.domain.market import MarketStream
    from strategy_engine.domain.ranges import TimeRange
    from strategy_engine.indicators.contracts import IndicatorRangeRequest
    from strategy_engine.strategies.contracts import LiveStrategySpec
    from strategy_engine.strategies.ema_pullback.contexts import build_context_bundle

    meta = market_fixture_meta()
    market = MarketStream(meta["ticker"], meta["timeframe"])
    time_range = TimeRange(meta["from_ms"], meta["to_ms"])
    out = {}
    with _slice_services() as services:
        for name, raw in _composite_corpus().items():
            plan = services.build_strategy_feature_plan.execute(
                LiveStrategySpec("ema_pullback", raw)  # type: ignore[arg-type]
            )
            frame = services.evaluate_indicator_range.execute(
                IndicatorRangeRequest(market, time_range, plan.indicator_plan)
            )
            bundle = build_context_bundle(raw, frame, plan)
            projection = build_historical_managed_projection(raw, frame, plan, bundle=bundle)
            out[name] = (raw, frame, plan, bundle, projection)
    return out


def _oracle(
    raw: dict[str, object], frame: object, plan: object, bundle: object, side: str, entry: int
) -> tuple[list[tuple[int, str, str | None]], list[tuple[str, float | None, str, tuple[str, ...]]]]:
    result = evaluate_managed_replay(
        raw,
        frame,  # type: ignore[arg-type]
        plan,  # type: ignore[arg-type]
        trade_id="T",
        side=side,  # type: ignore[arg-type]
        entry_time_ms=frame.time_ms[entry],  # type: ignore[attr-defined]
        entry_price=float(frame.market_bars[entry].close),  # type: ignore[attr-defined]
        bundle=bundle,  # type: ignore[arg-type]
    )
    return _events_and_bars(result)


def _events_and_bars(
    result: object,
) -> tuple[list[tuple[int, str, str | None]], list[tuple[str, float | None, str, tuple[str, ...]]]]:
    transitions = [
        (e.bar_index, str(e.rule_id), e.metadata.get("path_id"))  # type: ignore[misc]
        for e in result.events  # type: ignore[attr-defined]
        if e.event_type == "phase_changed"
    ]
    bars = [
        (b.phase, b.active_stop_price, b.active_take_profile, b.runtime_exit_rule_ids)
        for b in result.bars  # type: ignore[attr-defined]
    ]
    return transitions, bars


def _same_bars(
    projected: list[tuple[str, float | None, str, tuple[str, ...]]],
    expected: list[tuple[str, float | None, str, tuple[str, ...]]],
) -> bool:
    if len(projected) != len(expected):
        return False
    for got, want in zip(projected, expected, strict=True):
        if got[0] != want[0] or got[2] != want[2] or set(got[3]) != set(want[3]):
            return False
        if (got[1] is None) != (want[1] is None):
            return False
        if got[1] is not None and want[1] is not None and abs(got[1] - want[1]) > 1e-9:
            return False
    return True


def _corpus_mismatches(
    corpus: dict[str, tuple[dict[str, object], object, object, object, object]],
    *,
    fault: str | None = None,
    names: tuple[str, ...] | None = None,
) -> tuple[list[tuple[str, str, int]], int]:
    mismatches: list[tuple[str, str, int]] = []
    transitions_checked = 0
    for name, (raw, frame, plan, bundle, projection) in corpus.items():
        if names is not None and name not in names:
            continue
        for side in ("long", "short"):
            for entry in _CORPUS_ENTRIES:
                key = (name, side, entry)
                if key not in _ORACLE_CACHE:
                    _ORACLE_CACHE[key] = _oracle(raw, frame, plan, bundle, side, entry)
                want_transitions, want_bars = _ORACLE_CACHE[key]
                got_transitions: list[tuple[int, str, str | None]] = []
                got_bars = _replay_from_projection(
                    projection,  # type: ignore[arg-type]
                    frame.market_bars,  # type: ignore[attr-defined]
                    side=side,
                    entry_index=entry,
                    entry_price=float(frame.market_bars[entry].close),  # type: ignore[attr-defined]
                    target_index=len(frame.time_ms) - 1,  # type: ignore[attr-defined]
                    transitions=got_transitions,
                    fault=fault,
                )
                transitions_checked += len(want_transitions)
                if got_transitions != want_transitions or not _same_bars(got_bars, want_bars):
                    mismatches.append((name, side, entry))
    return mismatches, transitions_checked


def test_composite_projection_matches_managed_replay(composite_corpus) -> None:  # type: ignore[no-untyped-def]
    mismatches, transitions = _corpus_mismatches(composite_corpus)
    assert mismatches == []
    assert transitions >= 200, transitions
    # Every path of every spec wins somewhere in the corpus.
    won = {
        (name, path_id)
        for (name, _side, _entry), (transitions_, _) in _ORACLE_CACHE.items()
        for _, _, path_id in transitions_
    }
    assert won >= {
        ("owner_case", "fast"),
        ("owner_case", "htf"),
        ("mixed_at_least", "vote"),
        ("market_at_least", "vote"),
        ("trade_only_at_least", "trade"),
        ("trade_only_path", "trade"),
        ("trade_only_path", "market"),
        ("state_temporal", "regime"),
        ("state_temporal", "atom"),
        ("entry_change", "rise"),
        ("entry_change_at_least", "vote"),
    }, won


def test_composite_projection_matches_live_start_after_entry(composite_corpus) -> None:  # type: ignore[no-untyped-def]
    from decimal import Decimal as D

    from strategy_engine.strategies.ema_pullback.managed import (
        evaluate_start_after_entry_managed_projection,
    )

    checked = 0
    for raw, frame, plan, bundle, projection in composite_corpus.values():
        for side in ("long", "short"):
            for entry in _CORPUS_ENTRIES[::3]:
                price = D(str(frame.market_bars[entry].open))  # type: ignore[attr-defined]
                stop, take = (
                    (price * D("0.95"), price * D("1.1"))
                    if side == "long"
                    else (price * D("1.05"), price * D("0.9"))
                )
                live = evaluate_start_after_entry_managed_projection(
                    raw,
                    frame,  # type: ignore[arg-type]
                    plan,  # type: ignore[arg-type]
                    side=side,  # type: ignore[arg-type]
                    entry_time_ms=frame.time_ms[entry],  # type: ignore[attr-defined]
                    planned_entry_price=price,
                    initial_stop_price=stop,
                    initial_take_price=take,
                    target_time_ms=frame.time_ms[-1],  # type: ignore[attr-defined]
                    bundle=bundle,  # type: ignore[arg-type]
                )
                want, _ = _events_and_bars(live.replay)
                got: list[tuple[int, str, str | None]] = []
                _replay_from_projection(
                    projection,  # type: ignore[arg-type]
                    frame.market_bars,  # type: ignore[attr-defined]
                    side=side,
                    entry_index=entry,
                    entry_price=float(price),
                    target_index=len(frame.time_ms) - 1,  # type: ignore[attr-defined]
                    start_offset=1,
                    transitions=got,
                )
                assert got == want, (side, entry)
                checked += len(want)
    assert checked >= 50, checked


@pytest.mark.parametrize(
    ("fault", "names"),
    [
        ("ignore_mixed_trade_terms", ("mixed_at_least",)),
        ("drop_trade_only_at_least", ("trade_only_at_least",)),
        ("ignore_thresholds", ("owner_case",)),
        ("ignore_entry_changes", ("entry_change",)),
        ("anchor_one_bar_early", ("entry_change_at_least",)),
    ],
)
def test_consumer_faults_are_caught_by_the_corpus(  # type: ignore[no-untyped-def]
    composite_corpus, fault: str, names: tuple[str, ...]
) -> None:
    mismatches, _ = _corpus_mismatches(composite_corpus, fault=fault, names=names)
    assert mismatches, fault


def test_trade_only_at_least_parity(composite_corpus) -> None:  # type: ignore[no-untyped-def]
    """The owner's explicit case: `at_least 2 of [bars_in_trade, mfe_pct,
    mfe_atr]` is projected (not dropped) and resolves like `/managed-replay`."""

    mismatches, transitions = _corpus_mismatches(composite_corpus, names=("trade_only_at_least",))
    assert mismatches == []
    assert transitions > 0
    (rule,) = composite_corpus["trade_only_at_least"][4].rules
    (path,) = rule.paths
    assert path.at_least is not None and path.at_least.k == 2
    assert [term.trade_metric for term in path.at_least.terms] == [
        "bars_since_entry",
        "mfe_pct",
        "mfe_distance",
    ]
