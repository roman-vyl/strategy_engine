"""Rolling sum feature (OpenSpec `vol1h-rolling-sum-v1`): `rolling_sum` of any bar field
over `period` candles ending `lag` candles back, against a loop, missing until the window
is full or while it holds a missing value, on a higher timeframe as the last completed
candle; request validation, label, identity and live warm-up; and the vol1h composition
(last hour of volume over the hourly mean of the twenty days before it) through the
strategy pipeline on the BTCUSDT.P 5m fixture against a loop on the fixture volume."""

from __future__ import annotations

import gzip
import math
from typing import Any

import numpy as np
import pandas as pd
import pytest
from parity.corpus import _variant, base_spec
from parity.harness import FIXTURE_DIR, MARKET_FIXTURE
from test_ema_pullback_signed_only_if_e2e import _mask, _trace
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.feature_kinds import plan_feature_request
from strategy_engine.indicators.implementations.frame_ops import (
    align_completed_to_base,
    resample_ohlcv,
)
from strategy_engine.indicators.implementations.range_evaluator import resolve_feature
from strategy_engine.indicators.implementations.rolling_extreme import rolling_sum

Spec = dict[str, Any]


def _frame(bars: int, seed: int, gap: int | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-03", periods=bars, freq="5min", tz="UTC")
    c = 100 + np.cumsum(rng.normal(0, 1, bars))
    volume = rng.gamma(2.0, 50.0, bars)
    oi = 70_000 * np.exp(np.cumsum(rng.normal(0, 0.01, bars)))
    oi[: bars // 10] = math.nan
    if gap is not None:
        volume[gap] = math.nan
    return pd.DataFrame(
        {"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": volume, "open_interest": oi},
        index=index,
    )


def _loop(x: np.ndarray, period: int, lag: int) -> np.ndarray:
    out = np.full(len(x), math.nan)
    for t in range(period - 1 + lag, len(x)):
        window = x[t - lag - period + 1 : t - lag + 1]
        if np.isfinite(window).all():
            out[t] = window.sum()
    return out


@pytest.mark.parametrize("source", ["volume", "open_interest", "close"])
@pytest.mark.parametrize(("period", "lag"), [(12, 0), (96, 12), (1, 5)])
@pytest.mark.parametrize("gap", [None, 700])
def test_base_values_match_the_loop(source: str, period: int, lag: int, gap: int | None) -> None:
    frame = _frame(1500, 3, gap)
    got = rolling_sum(frame, source=source, period=period, lag=lag).to_numpy()
    expected = _loop(frame[source].to_numpy(), period, lag)
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0)
    np.testing.assert_array_equal(np.isnan(got), np.isnan(expected))
    assert np.isfinite(got).sum() > 500 and np.isnan(got).any()


def test_higher_timeframe_is_the_last_completed_candle() -> None:
    frame = _frame(2000, 4)
    htf = resample_ohlcv(frame, "1h")
    values = rolling_sum(htf, source="volume", period=3, lag=1)
    got = align_completed_to_base(values, timeframe="1h", base_index=frame.index).to_numpy()
    hourly = _loop(frame["volume"].resample("1h").sum().to_numpy(), 3, 1)
    hours = (frame.index.asi8 - frame.index.asi8[0]) // 3_600_000_000_000
    expected = np.where(hours >= 1, hourly[np.maximum(hours - 1, 0)], math.nan)
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0)
    np.testing.assert_array_equal(np.isnan(got), np.isnan(expected))


def test_request_label_identity_and_validation() -> None:
    lagged = plan_feature_request("rolling_sum", None, "volume", {"period": 5760, "lag": 12})
    assert lagged.output_id == "rolling_sum_volume_base_5760_lag12"
    plain = plan_feature_request("rolling_sum", None, None, {"period": 12})
    assert plain.output_id == "rolling_sum_volume_base_12_lag0"
    by_lag = resolve_feature(lagged, base_timeframe="5m", upstream={})
    by_period = resolve_feature(
        plan_feature_request("rolling_sum", None, "volume", {"period": 5760}),
        base_timeframe="5m",
        upstream={},
    )
    assert by_lag != by_period
    for source, params in (
        ("turnover", {"period": 3}),
        ("volume", {"period": 0}),
        ("volume", {"period": 3, "lag": -1}),
        ("volume", {"period": 3, "lag": 1.5}),
        ("volume", {"period": True}),
        ("volume", {"period": 3, "extra": 1}),
        ("volume", {}),
    ):
        with pytest.raises(InvalidRequestError):
            plan_feature_request("rolling_sum", None, source, params)


def test_live_warm_up_is_period_plus_lag() -> None:
    from strategy_engine.strategies.live_calculation.indicator_requirements import (
        ResolveIndicatorHistoryRequirements,
    )

    feature = plan_feature_request("rolling_sum", None, "volume", {"period": 5760, "lag": 12})
    assert ResolveIndicatorHistoryRequirements()._resolve_one(feature).bars == 5772


# vol1h: the last hour of 5m volume over the mean hour of the 20 days before it.
HOUR = 12
DAYS = 5760


def _sum(period: int, lag: int = 0) -> Spec:
    return {
        "feature": {
            "kind": "rolling_sum",
            "source": "volume",
            "params": {"period": period, "lag": lag},
        }
    }


VOL1H = {
    "ratio": {
        "left": _sum(HOUR),
        "right": {"ratio": {"left": _sum(DAYS, HOUR), "right": {"const": DAYS / HOUR}}},
    }
}


def _probe() -> Spec:
    branch = {
        "kind": "range",
        "operand": VOL1H,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": [{"child_id": "vol1h", "predicate": branch}],
            "paths": [{"path_id": "pass", "require": ["vol1h"]}],
        },
    }


def _fixture_volume() -> np.ndarray:
    import json

    payload = json.loads(gzip.decompress((FIXTURE_DIR / MARKET_FIXTURE).read_bytes()))
    return np.array([float(c["volume"]) for c in payload["candles"]])


def _research_vol1h(v: np.ndarray) -> np.ndarray:
    out = np.full(len(v), math.nan)
    for i in range(DAYS + HOUR - 1, len(v)):
        hv = v[i - HOUR - DAYS + 1 : i - HOUR + 1].sum() / (DAYS / HOUR)
        if hv > 0:
            out[i] = v[i - HOUR + 1 : i + 1].sum() / hv
    return out


def test_vol1h_through_the_pipeline_matches_the_loop() -> None:
    spec = base_spec()
    spec["setups"] = [_probe()]
    recorder, context = _run([_variant("probe", spec)])
    (capture,) = recorder.captures
    volume = _fixture_volume()
    for side in ("long", "short"):
        got = _trace(_mask(capture, side), "vol1h")
        expected = _research_vol1h(volume)[-len(got) :]
        assert np.isfinite(expected).sum() > 1000
        np.testing.assert_allclose(got, expected, rtol=1e-9, atol=0)
        np.testing.assert_array_equal(np.isnan(got), np.isnan(expected))
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.ratio") >= 2
