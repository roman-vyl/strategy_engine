import numpy as np
import pytest
from test_ema_pullback_forming_candle import _operand, _parse

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.forming_candle import forming_range_values
from strategy_engine.strategies.ema_pullback.live_calculation_requirements import _predicate_history


def test_contract():
    assert _parse(_operand()).long.operand == _parse(_operand(field="body")).long.operand
    parsed = _parse(_operand(field="range"))
    assert parsed.long.operand.forming_candle.field == "range"
    assert any(r.timeframe == "1h" and r.bars == 1 for r in _predicate_history(parsed, "test"))
    for field in ("bad", None, [], 1):
        with pytest.raises(InvalidRequestError):
            _parse(_operand(field=field))


def test_boundaries_future_and_missing():
    t = np.arange(12) * 5
    h = np.arange(12.0) + 100
    low = np.full(12, 99.0)
    a = np.repeat([2.0, 4.0, 8.0], 4)
    actual = forming_range_values(t, h, low, a, 20, 5)
    np.testing.assert_allclose(actual, (h - low) / a)
    h[8:] = 10000
    np.testing.assert_array_equal(forming_range_values(t, h, low, a, 20, 5)[:8], actual[:8])
    out = forming_range_values(t[1:], h[1:], low[1:], a[1:], 20, 5)
    assert np.isnan(out[:3]).all()
    np.testing.assert_array_equal(out[3:7], actual[4:8])
    h[1] = np.nan
    assert np.isnan(forming_range_values(t, h, low, a, 20, 5)[1:4]).all()
    assert forming_range_values(t, low, low, a, 20, 5)[0] == 0
    a[0] = 0
    assert np.isnan(forming_range_values(t, h, low, a, 20, 5)[:4]).all()


def test_gap_and_frozen_denominator():
    t = np.array([0, 5, 15, 20, 25])
    out = forming_range_values(t, np.ones(5) * 2, np.ones(5), np.array([2, 99, 99, 4, 99]), 20, 5)
    np.testing.assert_allclose(out, [0.5, 0.5, np.nan, 0.25, 0.25], equal_nan=True)


def test_manifest_pipeline():
    import json
    from pathlib import Path

    from parity.corpus import _variant
    from test_ema_pullback_stack_episode_e2e import _run

    spec = json.loads(Path("examples/forming-candle-range.json").read_text())
    _run([_variant("forming-range", spec)])


def test_complete_prefix_matches_full():
    t = np.arange(40) * 5
    high = 100 + np.sin(np.arange(40))
    low = high - 2
    atr = np.repeat(np.arange(1.0, 11.0), 4)
    full = forming_range_values(t, high, low, atr, 20, 5)
    prefix = forming_range_values(t[8:27], high[8:27], low[8:27], atr[8:27], 20, 5)
    np.testing.assert_array_equal(prefix, full[8:27])
