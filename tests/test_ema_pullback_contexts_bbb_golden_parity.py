from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.domain.validity import Validity
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.contexts import build_context_bundle
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)


def _legacy_module():
    path = (
        Path(__file__).parents[1]
        / "legacy_source/bbb/research/strategies/ema_pullback/components/context.py"
    )
    spec = importlib.util.spec_from_file_location("legacy_ema_pullback_context", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spec() -> dict[str, object]:
    return {
        "anchor_stack": {
            "fast": {"source": "close", "timeframe": "base", "period": 2},
            "anchor": {"source": "close", "timeframe": "base", "period": 3},
            "slow": {"source": "close", "timeframe": "base", "period": 5},
        },
        "components": {"blockers": []},
        "setups": [],
        "contexts": {
            "htf": {
                "component_id": "htf_context",
                "timeframe": "1h",
                "source": "close",
                "fast_period": 2,
                "anchor_period": 3,
                "slow_period": 5,
            }
        },
        "trade_management": {
            "exit_policy": {
                "always_on": {"exits": []},
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {},
        },
    }


def test_context_state_and_masks_match_legacy_bbb() -> None:
    values = {
        "ema_close_1h_2": (None, None, "3", "1", "2"),
        "ema_close_1h_3": (None, None, "2", "2", "2"),
        "ema_close_1h_5": (None, None, "1", "3", "2"),
    }
    frame = FeatureFrame(
        market=MarketStream("BTCUSDT.P", "5m"),
        requested_range=TimeRange(0, 1_500_000),
        time_ms=(0, 300_000, 600_000, 900_000, 1_200_000),
        series=values,
        validity={key: Validity(None, 0, True, None) for key in values},
        plan_hash="plan",
        market_data_hash="market",
    )
    raw_spec = _spec()
    output = build_context_bundle(
        raw_spec,
        frame,
        build_feature_plan_from_canonical_spec(raw_spec),
    ).outputs[0]

    legacy = _legacy_module()
    legacy_frame = pd.DataFrame(
        {
            key: [float(item) if item is not None else None for item in series]
            for key, series in values.items()
        }
    )
    masks = legacy.htf_context(
        legacy_frame,
        fast_col="ema_close_1h_2",
        anchor_col="ema_close_1h_3",
        slow_col="ema_close_1h_5",
    )
    assert list(output.state) == masks.state_series().tolist()
    assert list(output.up) == masks.up.tolist()
    assert list(output.down) == masks.down.tolist()
    assert list(output.neutral) == masks.neutral.tolist()
