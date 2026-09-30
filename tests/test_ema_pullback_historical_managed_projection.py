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

from decimal import Decimal

import pytest

from strategy_engine.domain.market import MarketBar, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.contracts import HistoricalManagedProjection
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


def _replay_from_projection(
    projection: HistoricalManagedProjection,
    market_bars: tuple[MarketBar, ...],
    *,
    side: str,
    entry_index: int,
    entry_price: float,
    target_index: int,
) -> list[tuple[str, float | None, str, tuple[str, ...]]]:
    phase_rules = [r for r in projection.rules if r.kind == "phase_transition"]
    stop_rules = [r for r in projection.rules if r.kind == "stop_action"]
    take_rules = [r for r in projection.rules if r.kind == "take_action"]
    runtime_rules = [r for r in projection.rules if r.kind == "runtime_exit"]

    phase = "initial_risk"
    active_stop_price: float | None = None
    active_take_profile = "initial"
    best_price = entry_price
    out: list[tuple[str, float | None, str, tuple[str, ...]]] = []

    for index in range(entry_index, target_index + 1):
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
        }

        for rule in phase_rules:
            if _RANK[rule.target_phase] <= _RANK[phase]:
                continue
            if rule.condition_id is not None:
                series = projection.conditions[rule.condition_id]
                met = (series.long if side == "long" else series.short)[index]
            else:
                assert rule.distance_id is not None and rule.trade_metric is not None
                threshold = projection.distances[rule.distance_id][index]
                met = trade_metric_values[rule.trade_metric] >= threshold
            if met:
                phase = rule.target_phase

        candidates: list[float] = []
        for rule in stop_rules:
            if not _at_least(phase, rule.activation_phase):
                continue
            distance = projection.distances[rule.distance_id][index]
            if distance != distance:  # NaN: "not ready this bar", per contract convention
                continue
            price = entry_price + distance if side == "long" else entry_price - distance
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
