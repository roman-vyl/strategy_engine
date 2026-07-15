# ATR Indicator Vertical Slice v1

## Scope

This change ports BBB-compatible Average True Range into the independent Indicator Engine. It does not port ATR-distance features, RSI, ADX/DI, strategy feature planning, or live incremental state.

## Authoritative BBB semantics

Copied from `legacy_source/bbb/research/strategies/ema_pullback/features/calculations.py`:

```python
prev_close = close.shift(1)
h_l = high - low
h_pc = (high - prev_close).abs()
l_pc = (low - prev_close).abs()
true_range = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
atr = true_range.rolling(window=period, min_periods=period).mean()
```

This is intentionally a simple rolling mean. It is not Wilder smoothing.

## API capability

`atr` is now returned by:

```http
GET /v1/indicators
GET /v1/indicators/atr/schema
```

A range request uses the existing endpoint:

```http
POST /v1/indicator-evaluations/range
```

Example planned feature:

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

`source="close"` is retained because current BBB `FeaturePlan` uses that structural value, even though ATR consumes high, low, and close.

## Higher-timeframe semantics

HTF OHLCV is resampled left-closed and left-labelled. ATR is calculated on the HTF frame, shifted by one full HTF interval, then forward-filled onto the base grid. An incomplete HTF candle cannot leak into the current base-timeframe result.

## Implementation boundaries

- `atr.py`: validation, true range, rolling ATR formula.
- `frame_ops.py`: shared MarketFrame conversion, resampling, completion alignment, Decimal serialization.
- `range_evaluator.py`: one market read and shared timeframe cache for EMA and ATR.
- `registries.py`: catalog/schema and validation dispatch.

## Parity evidence

Golden tests execute the copied BBB calculations module directly and compare:

- base ATR period 3;
- base ATR period 14;
- 1h ATR period 2 aligned to 5m bars;
- every numeric and null/warmup position.

Mixed EMA+ATR API acceptance also verifies that both series are calculated from one Market Data Service read.
