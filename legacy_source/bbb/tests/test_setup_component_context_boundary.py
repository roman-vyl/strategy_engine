"""Guardrails: setup components stay context-unaware (task 2.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pandas")

import pandas as pd

from research.strategies.ema_pullback.component_builders import (
    ema_bounce_counter_setup_spec,
    setup_rule,
)
from research.strategies.ema_pullback.components.registry import (
    EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
    UNTOUCHED_ANCHOR_SETUP_COMPONENT,
    resolve_component,
)
from research.strategies.ema_pullback.context.evaluation import evaluate_context_consumption
from research.strategies.ema_pullback.features.calculations import add_feature_columns_from_plan
from research.strategies.ema_pullback.features.plan import build_feature_plan_from_strategy_spec
from research.strategies.ema_pullback.setup_runtime import run_setup_mask, run_setup_trace
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec

_SETUP_MODULE = Path(__file__).resolve().parents[1] / "research/strategies/ema_pullback/components/setup.py"


def _ohlcv(periods: int = 8) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01 10:00", periods=periods, freq="5min", tz="UTC")
    close = pd.Series(100.0, index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1.0,
        },
        index=idx,
    )


def test_setup_component_module_has_no_context_evaluator_imports() -> None:
    source = _SETUP_MODULE.read_text(encoding="utf-8")
    forbidden = (
        "evaluate_context_consumption",
        "ContextBundle",
        "context.evaluation",
        "context.bundle",
    )
    hits = [name for name in forbidden if name in source]
    assert hits == [], f"setup.py must not reference context layer: {hits}"


def test_run_setup_mask_and_trace_never_call_evaluate_context_consumption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def _spy(consumption, ctx):  # type: ignore[no-untyped-def]
        calls.append((consumption.policy.policy_id, ctx.evaluated_side))
        return evaluate_context_consumption(consumption, ctx)

    monkeypatch.setattr(
        "research.strategies.ema_pullback.context.evaluation.evaluate_context_consumption",
        _spy,
    )

    spec = make_ema_pullback_strategy_spec(enabled_sides=("long",))
    plan = build_feature_plan_from_strategy_spec(spec)
    df = add_feature_columns_from_plan(_ohlcv(), plan)
    anchor_col = plan.anchor_columns["anchor"]

    untouched_rule = spec.setups[0]
    assert untouched_rule.component_id == UNTOUCHED_ANCHOR_SETUP_COMPONENT
    run_setup_mask(df, untouched_rule, plan, anchor_col=anchor_col, side="long")
    run_setup_trace(df, untouched_rule, plan, anchor_col=anchor_col, side="long")

    bounce_rule = setup_rule(
        instance_id="bounce_counter",
        component_id=EMA_BOUNCE_COUNTER_SETUP_COMPONENT,
        params=ema_bounce_counter_setup_spec(
            max_bounces=3,
            touch_lookback_bars=3,
        ),
    )
    bounce_plan = build_feature_plan_from_strategy_spec(
        make_ema_pullback_strategy_spec(
            enabled_sides=("long",),
            setups=(bounce_rule,),
        )
    )
    bounce_df = add_feature_columns_from_plan(_ohlcv(), bounce_plan)
    bounce_cols = bounce_plan.setup_columns_for("bounce_counter")
    bounce_df[bounce_cols["fast"]] = 110.0
    bounce_df[bounce_cols["anchor"]] = 100.0
    bounce_df[bounce_cols["slow"]] = 90.0
    run_setup_mask(bounce_df, bounce_rule, bounce_plan, anchor_col=anchor_col, side="long")
    run_setup_trace(bounce_df, bounce_rule, bounce_plan, anchor_col=anchor_col, side="long")

    untouched_fn = resolve_component("setup", UNTOUCHED_ANCHOR_SETUP_COMPONENT).func
    untouched_fn(bounce_df, anchor_col, 50, 3, side="long")

    bounce_fn = resolve_component("setup", EMA_BOUNCE_COUNTER_SETUP_COMPONENT).func
    bounce_fn(
        bounce_df,
        bounce_cols["fast"],
        bounce_cols["anchor"],
        bounce_cols["slow"],
        max_bounces=3,
        touch_lookback_bars=3,
        side="long",
    )

    assert calls == []
