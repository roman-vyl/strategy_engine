# Specification: ATR Indicator Vertical Slice v1

## Requirement: ATR catalog capability

The Indicator Engine SHALL advertise `atr` through `/v1/indicators` and SHALL expose a schema through `/v1/indicators/atr/schema`.

## Requirement: Strict ATR plan validation

An ATR planned feature SHALL require `source="close"`, one positive integer `period`, no additional parameters, and no feature dependencies. Invalid plans SHALL fail before Market Data Service is called.

## Requirement: BBB-compatible true range

The engine SHALL compute true range as the row-wise maximum of `high-low`, `abs(high-prev_close)`, and `abs(low-prev_close)` using the same missing-value behavior as BBB pandas calculations.

## Requirement: BBB-compatible ATR smoothing

The engine SHALL calculate ATR as `true_range.rolling(window=period, min_periods=period).mean()`. It SHALL NOT substitute Wilder RMA, EWM, or another smoothing algorithm.

## Requirement: Warmup semantics

For a base-timeframe series with sufficient data, the first ATR output SHALL occur at index `period-1`. Earlier outputs SHALL be JSON null. Validity metadata SHALL report that index as `warmup_bars` and the corresponding bar open time as `valid_from_ms`.

## Requirement: Completed higher-timeframe semantics

For a non-base ATR timeframe, the engine SHALL resample left-closed OHLCV, calculate ATR on HTF bars, shift results by one HTF duration, and forward-fill onto the base grid. Incomplete HTF candles SHALL NOT affect visible output.

## Requirement: Shared market read

One indicator plan containing EMA and ATR SHALL load the requested market range once and calculate both features from the same immutable MarketFrame.

## Requirement: Golden parity

Automated tests SHALL execute the copied BBB `features/calculations.py` and compare base and HTF ATR output position by position, including null/warmup positions.
