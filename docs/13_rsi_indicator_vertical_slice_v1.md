# RSI Indicator Vertical Slice v1

## Status

Implemented in the sandbox with direct golden parity against the copied BBB calculations module.

## Authoritative BBB behavior

RSI is a simple rolling-mean implementation:

```text
delta = close.diff()
gain = delta.clip(lower=0)
loss = (-delta).clip(lower=0)
avg_gain = rolling_mean(gain, period)
avg_loss = rolling_mean(loss, period)
rsi = 100 - 100 / (1 + avg_gain / avg_loss)
```

It is not Wilder RMA. The first delta is missing, so the first finite base-timeframe output normally appears at index `period`.

For HTF features, BBB resamples OHLCV with left-closed buckets, computes RSI on HTF close, shifts the result by one full HTF interval, then forward-fills it onto the base grid. The new engine preserves that completion boundary exactly.

## API contract

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

The response uses normalized decimal text and `null` during warmup. Validity metadata identifies the first finite base-grid value.

## Verification

- base RSI periods 3 and 14 match the copied BBB implementation value-by-value;
- completed `1h` RSI period 3 matches value-by-value and null-for-null;
- invalid source, period, extra parameters, and dependencies are rejected before any MDS call;
- EMA, ATR, and RSI share one MarketFrame and one MDS range read in a mixed plan.
