# RSI Indicator Vertical Slice v1 Specification

## Purpose

Define the calculation, validation, higher-timeframe visibility, and public API for the RSI indicator vertical slice.
## Requirements
### Requirement: BBB-compatible RSI

The Indicator Engine SHALL calculate RSI using simple rolling means of gains and losses with `window=period` and `min_periods=period`. It SHALL NOT substitute Wilder RMA or exponential smoothing.

#### Scenario: Calculate BBB-compatible RSI

- **WHEN** RSI is evaluated for an ordered close series
- **THEN** gains and losses SHALL use simple rolling means with the configured period
- **AND** the result SHALL NOT use Wilder RMA or exponential smoothing.

### Requirement: Plan validation

RSI SHALL require `source="close"`, one strict positive integer `period`, no extra parameters, and no dependencies.

#### Scenario: Reject an invalid RSI plan

- **WHEN** an RSI feature has an invalid source, period, extra parameter, or dependency
- **THEN** validation SHALL reject the feature before market data is loaded.

### Requirement: Completed HTF visibility

For higher-timeframe RSI, values SHALL become visible on the base grid only after the source HTF bucket is complete.

#### Scenario: Higher-timeframe RSI bucket is incomplete

- **WHEN** a higher-timeframe RSI source bucket has not completed
- **THEN** its value SHALL NOT be visible on the base-timeframe grid.

### Requirement: Public capability

The catalog and schema APIs SHALL advertise `rsi`. The range evaluation API SHALL return RSI as Decimal text or `null`, with deterministic validity metadata.

#### Scenario: Evaluate RSI through the public API

- **WHEN** a valid RSI range evaluation is requested
- **THEN** the catalog and schema APIs SHALL advertise `rsi`
- **AND** the response SHALL contain normalized decimal text or `null` with deterministic validity metadata.
