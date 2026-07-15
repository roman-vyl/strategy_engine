# EMA Indicator Vertical Slice v1 Specification

## Requirement: EMA catalog capability

The indicator catalog SHALL expose `ema` with a stable schema describing source, timeframe, positive integer period, one value output, batch support, and incremental support as false.

## Requirement: BBB-compatible EMA formula

For each source series, EMA SHALL equal pandas `ewm(span=period, adjust=False).mean()` on the same ordered values.

## Requirement: Completed HTF alignment

For a feature timeframe above the base timeframe, the engine SHALL resample left-labeled/left-closed OHLCV, compute EMA on the completed aggregate series, shift the result by one feature timeframe, and forward-fill it onto the base-timeframe grid. No value from an incomplete HTF candle may be visible early.

## Requirement: Exact range input semantics

The evaluator SHALL calculate from the MarketFrame supplied for the exact requested range. It SHALL NOT silently request earlier warmup bars in this change.

## Requirement: Stable range result

The response SHALL preserve the requested base-time axis, caller-provided output IDs, deterministic plan hash, MDS market-data hash, normalized decimal-text values, and nulls where no completed HTF value exists.

## Requirement: Honest capability boundaries

Only EMA range evaluation becomes supported. Other indicator kinds and strategy evaluations SHALL continue to return `unsupported_capability` rather than fake success.

## Requirement: Golden parity

Acceptance SHALL execute the copied BBB EMA calculation implementation against representative base and HTF fixtures and compare every output position with the new engine.
