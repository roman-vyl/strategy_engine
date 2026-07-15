# Design: RSI Indicator Vertical Slice v1

## Semantics copied from BBB

```text
delta = close.diff()
gain = delta.clip(lower=0)
loss = (-delta).clip(lower=0)
avg_gain = gain.rolling(window=period, min_periods=period).mean()
avg_loss = loss.rolling(window=period, min_periods=period).mean()
rs = avg_gain / avg_loss
rsi = 100 - 100 / (1 + rs)
```

This is a simple rolling-mean RSI, not Wilder RMA. Because the first delta is missing, the first finite RSI normally appears at zero-based index `period`.

## Higher timeframe behavior

OHLCV is resampled with left labels and left-closed buckets. RSI is calculated on the resampled close series. The feature timestamp is shifted by one complete higher-timeframe interval and forward-filled onto the base grid. An incomplete HTF candle cannot affect the result.

## Public plan contract

```json
{
  "output_id": "rsi_1h_14",
  "kind": "rsi",
  "timeframe": "1h",
  "source": "close",
  "parameters": {"period": 14},
  "dependencies": []
}
```

## Boundaries

`rsi.py` owns validation and the formula. `frame_ops.py` continues to own resampling/alignment. `range_evaluator.py` dispatches registered capabilities and assembles the shared `FeatureFrame`. HTTP and MDS adapters remain unchanged.
