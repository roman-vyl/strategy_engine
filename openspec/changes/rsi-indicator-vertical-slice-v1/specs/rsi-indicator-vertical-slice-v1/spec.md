# RSI Indicator Vertical Slice v1 Specification

## Requirement: BBB-compatible RSI

The Indicator Engine SHALL calculate RSI using simple rolling means of gains and losses with `window=period` and `min_periods=period`. It SHALL NOT substitute Wilder RMA or exponential smoothing.

## Requirement: Plan validation

RSI SHALL require `source="close"`, one strict positive integer `period`, no extra parameters, and no dependencies.

## Requirement: Completed HTF visibility

For higher-timeframe RSI, values SHALL become visible on the base grid only after the source HTF bucket is complete.

## Requirement: Public capability

The catalog and schema APIs SHALL advertise `rsi`. The range evaluation API SHALL return RSI as Decimal text or `null`, with deterministic validity metadata.

## Requirement: Golden parity

Tests SHALL execute the copied BBB calculations module and compare base and HTF RSI value-by-value, including exact missing-value placement.
