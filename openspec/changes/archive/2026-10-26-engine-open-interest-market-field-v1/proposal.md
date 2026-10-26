## Why

MDS now returns `open_interest` as a nullable field of every candle (MDS #22, deployed 2026-10-26). The Engine already accepts and
validates the field (`engine-mds-candle-open-interest-input-v1`, dd1ce62), but drops the value. Owner decision 2026-10-26: open interest
becomes a market field of the Engine **exactly like `volume`**, with one difference: it is optional.

This is stage A: the value is no longer lost, and the computation layer can read it. Using OI in strategy conditions is stage B, a
separate change.

## What Changes

- `MarketBar` gets `open_interest: Decimal | None`, defaulting to `None`. `None` means MDS has no OI for that bar: an instrument without
  OI, a bar before the start of OI history, or a stream other than 5m.
- `MarketDataServiceClient.load_range` puts the validated value on the bar (`parse_decimal_text`, the same conversion as `volume`)
  instead of dropping it, for both `/v1/candles` and `/v1/historical-candles`.
- `MarketArrays`, the shared float64 view built once per evaluation and per range batch, serves `open_interest` through the same
  lazy, cached `values(field)` and `array(field)` as the OHLCV fields: `float(bar.open_interest)` per bar, and **NaN** where the bar has
  `None`. There is no forward fill, no zero, and no shift to another bar. Every candidate of a batch reads the same array.
- Unchanged: the OHLCV field set (`OHLCV_FIELDS`), `ohlcv_columns()`, `dataframe()` and so every indicator frame, the FeaturePlan and
  the feature-kind registry, predicates and operands (`_PRICE_FIELDS` stays open/high/low/close), the FeatureFrame public format,
  `market_data_hash`, the Runtime and Research contracts, and every strategy result. A strategy that does not read OI computes exactly
  what it computed before.

Not in this change (stage B): OI as an operand or feature kind in strategies, rules for NaN in conditions, HTF aggregation of OI.

## Impact

- `src/strategy_engine/domain/market.py`, `adapters/market_data_service/client.py`, `indicators/market_arrays.py`; tests.
- Spec deltas: MODIFIED *Accept optional open interest on historical candles* (`mds-historical-read-consumer-v1`), MODIFIED *Build one
  complete live FeatureFrame* (`live-feature-frame-acquisition-v1`), ADDED *Open interest in the shared market arrays*
  (`batch-computation-reuse`).
