# Design: ATR Indicator Vertical Slice v1

## Semantics copied from BBB

For each bar:

```text
prev_close = close.shift(1)
true_range = max(
  high - low,
  abs(high - prev_close),
  abs(low - prev_close)
)
atr = true_range.rolling(window=period, min_periods=period).mean()
```

This is a simple rolling mean, not Wilder RMA and not exponential smoothing. The first true-range value uses `high-low` because previous close is absent and pandas row-wise max skips missing values. The first ATR value therefore appears at zero-based index `period-1`.

## Higher timeframe behavior

OHLCV is resampled with `label="left", closed="left"`. ATR is calculated on the resampled frame. The resulting series is shifted by one complete HTF interval and forward-filled onto the base grid. No value from an incomplete HTF candle may be visible.

## Module boundaries

```text
implementations/atr.py
  - ATR validation
  - true range
  - rolling ATR formula

implementations/frame_ops.py
  - MarketFrame -> pandas conversion
  - OHLCV resampling
  - completed HTF alignment
  - Decimal-text serialization

implementations/range_evaluator.py
  - one MDS frame
  - shared timeframe cache
  - dispatch registered EMA/ATR calculations
  - FeatureFrame assembly
```

The HTTP route and MDS client remain unchanged. Registry wiring exposes the new capability.

## Compatibility contract

A BBB planned ATR feature maps to:

```json
{
  "output_id": "atr_base_14",
  "kind": "atr",
  "timeframe": "base",
  "source": "close",
  "parameters": {"period": 14},
  "dependencies": []
}
```

`source="close"` is retained for structural parity with the current BBB `PlannedFeature`, although the calculation consumes high, low, and close.
