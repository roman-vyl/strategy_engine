# EMA Indicator Vertical Slice v1

## Status

Implemented in the sandbox.

## Ported BBB semantics

The implementation is a semantic port of:

`legacy_source/bbb/research/strategies/ema_pullback/features/calculations.py`

Preserved behavior:

- pandas float64 calculation;
- `Series.ewm(span=period, adjust=False).mean()`;
- no `min_periods` warmup for base EMA;
- HTF OHLCV resampling with `label="left"` and `closed="left"`;
- HTF feature visibility only after the aggregate candle completes;
- forward-fill of completed HTF EMA values onto the base grid.

## Public capability

The catalog now exposes `ema` and its schema. The existing endpoint is operational:

```http
POST /v1/indicator-evaluations/range
```

Example feature:

```json
{
  "output_id": "ema_close_base_200",
  "kind": "ema",
  "timeframe": "base",
  "source": "close",
  "parameters": {"period": 200},
  "dependencies": []
}
```

A canonical textual timeframe equal to the market base timeframe is also accepted. Higher integral timeframes such as `1h` are resampled and completion-aligned.

## Boundary behavior

The caller supplies ticker, base timeframe, exact half-open range, and IndicatorPlan. The service loads canonical candles from MDS, calculates EMA internally, and returns the base time axis, Decimal-text series, validity metadata, plan hash, and market-data hash.

The slice deliberately calculates from the exact requested MarketFrame. It does not yet extend the request backwards for prior EMA state. BBB parity is therefore defined for identical bounded input frames. History extension, cache reuse, and incremental state are later changes.

## Validation

EMA requires:

- source in `open|high|low|close`;
- strict positive integer `period`;
- no feature dependencies;
- only the `period` parameter;
- base or integral higher timeframe.

Validation occurs before MDS is called.

## Verification

- base EMA exact examples;
- HTF completion visibility;
- request and schema validation;
- FastAPI range evaluation with fake MDS;
- unsupported capability preservation;
- golden parity by dynamically executing the copied BBB calculation module for base periods 3 and 11 and HTF 1h period 2.
