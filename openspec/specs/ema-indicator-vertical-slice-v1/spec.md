# EMA Indicator Vertical Slice v1 Specification

## Purpose

Define the supported EMA indicator range-evaluation slice, including BBB-compatible calculation, completed higher-timeframe alignment, stable outputs, and parity acceptance.

## Requirements

### Requirement: EMA catalog capability

The indicator catalog SHALL expose `ema` with a stable schema describing source, timeframe, positive integer period, one value output, batch support, and incremental support as false.

#### Scenario: Inspect the EMA catalog entry

- **WHEN** a caller lists indicators or requests the EMA schema
- **THEN** the catalog SHALL expose the stable EMA inputs, period, output, and capability flags.

### Requirement: BBB-compatible EMA formula

For each source series, EMA SHALL equal pandas `ewm(span=period, adjust=False).mean()` on the same ordered values.

#### Scenario: Evaluate a base-timeframe EMA

- **WHEN** an EMA feature is evaluated on an ordered base-timeframe source series
- **THEN** every output SHALL match pandas `ewm(span=period, adjust=False).mean()` for that series.

### Requirement: Completed HTF alignment

For a feature timeframe above the base timeframe, the engine SHALL resample left-labeled/left-closed OHLCV, compute EMA on the completed aggregate series, shift the result by one feature timeframe, and forward-fill it onto the base-timeframe grid. No value from an incomplete HTF candle may be visible early.

#### Scenario: Higher-timeframe bucket is incomplete

- **WHEN** a higher-timeframe EMA bucket has not reached its completion boundary
- **THEN** its value SHALL NOT be visible on the base-timeframe grid
- **AND** the last completed value MAY be forward-filled after its completion boundary.

### Requirement: Exact range input semantics

The evaluator SHALL calculate from the MarketFrame supplied for the exact requested range. It SHALL NOT silently request earlier warmup bars in this change.

#### Scenario: Evaluate a bounded market frame

- **WHEN** the evaluator receives a MarketFrame for an exact requested range
- **THEN** it SHALL calculate only from that frame
- **AND** SHALL NOT request earlier warmup candles.

### Requirement: Stable range result

The response SHALL preserve the requested base-time axis, caller-provided output IDs, deterministic plan hash, MDS market-data hash, normalized decimal-text values, and nulls where no completed HTF value exists.

#### Scenario: Serialize an EMA range result

- **WHEN** EMA range evaluation succeeds
- **THEN** the response SHALL preserve the time axis, output IDs, plan hash, and MDS hash
- **AND** SHALL serialize values as normalized decimal text or `null`.

### Requirement: Honest capability boundaries

Only EMA range evaluation becomes supported. Other indicator kinds and strategy evaluations SHALL continue to return `unsupported_capability` rather than fake success.

#### Scenario: Request an unported capability at this slice boundary

- **WHEN** a capability outside the EMA vertical slice is requested before its own porting change
- **THEN** the service SHALL return `unsupported_capability`
- **AND** SHALL NOT fabricate a successful result.

### Requirement: Golden parity

Acceptance SHALL execute the copied BBB EMA calculation implementation against representative base and HTF fixtures and compare every output position with the new engine.

#### Scenario: Run the EMA parity suite

- **WHEN** representative base and higher-timeframe EMA fixtures are evaluated
- **THEN** every output and null position SHALL match the copied BBB calculation implementation.
