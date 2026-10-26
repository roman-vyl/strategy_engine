## Why

Market Data Service will add open interest (OI) to the candles it already returns from `GET /v1/candles` and
`POST /v1/historical-candles` (owner decision 2026-10-25: one response with OHLCV and OI, no request flag, no separate route).
Today the Engine reads each candle with a strict model that rejects unknown fields (`CandlePayload`, `extra="forbid"`). If MDS
started sending `open_interest` first, every live and historical evaluation would fail with `upstream_contract_error`.

Agreed deploy order:

1. MDS stream bounds (done, MDS #20).
2. **Engine accepts the optional OI field** (this change).
3. MDS starts returning OI in the candle API.
4. Engine uses OI as a feature kind (`open_interest`) in the FeaturePlan.
5. Research components.

## What Changes

- Each candle in an MDS candle range response MAY carry `open_interest`: decimal text, `null`, or absent. Absent and `null`
  mean the same: no OI value for that bar.
- A present non-null value SHALL be finite decimal text; anything else (number, boolean, object, non-decimal text) is a broken
  MDS contract and the whole response is rejected as `upstream_contract_error`, as for a bad OHLCV value.
- The value is validated and then **not used**: it is not stored on `MarketBar`, not put into the FeatureFrame, not used by any
  indicator, component or projection, and not returned to Runtime or Research.
- Any other unknown field on a candle or on the range envelope is still rejected.
- Unchanged: OHLCV parsing, the gap/order/identity/completeness checks, `market_data_hash` (consumed as returned by MDS, never
  recomputed), the bounds adapter (`market_stream_bounds.v1`), Runtime and Research contracts, all strategy results.

Not in this change: carrying OI into the feature pipeline, the `open_interest` feature kind, OI indicators or components, any
MDS change, deploy.

## Impact

- `src/strategy_engine/adapters/market_data_service/models.py` (`CandlePayload`) and `client.py` (`load_range`).
- Tests in `tests/test_mds_client.py`.
- Spec deltas: `mds-historical-read-consumer-v1` (historical endpoint) and `live-feature-frame-acquisition-v1` (live
  candle read).
