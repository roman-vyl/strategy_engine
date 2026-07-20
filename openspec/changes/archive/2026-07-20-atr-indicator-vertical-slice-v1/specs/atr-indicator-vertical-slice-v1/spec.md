# ATR Indicator Vertical Slice v1 Specification

## ADDED Requirements

### Requirement: ATR catalog capability

The Indicator Engine SHALL advertise `atr` through `/v1/indicators` and SHALL expose a schema through `/v1/indicators/atr/schema`.

#### Scenario: Inspect the ATR catalog entry

- **WHEN** a caller lists indicators or requests the ATR schema
- **THEN** the catalog SHALL advertise `atr` and return its schema.

### Requirement: Strict ATR plan validation

An ATR planned feature SHALL require `source="close"`, one positive integer `period`, no additional parameters, and no feature dependencies. Invalid plans SHALL fail before Market Data Service is called.

#### Scenario: Reject an invalid ATR plan before loading market data

- **WHEN** an ATR feature has an invalid source, period, extra parameter, or dependency
- **THEN** validation SHALL fail before Market Data Service is called.

### Requirement: BBB-compatible true range

The engine SHALL compute true range as the row-wise maximum of `high-low`, `abs(high-prev_close)`, and `abs(low-prev_close)` using the same missing-value behavior as BBB pandas calculations.

#### Scenario: Calculate true range with BBB missing-value behavior

- **WHEN** ATR evaluates an ordered OHLC series
- **THEN** each true-range value SHALL use the BBB row-wise maximum formula
- **AND** the first value SHALL use `high-low` when previous close is absent.

### Requirement: BBB-compatible ATR smoothing

The engine SHALL calculate ATR as `true_range.rolling(window=period, min_periods=period).mean()`. It SHALL NOT substitute Wilder RMA, EWM, or another smoothing algorithm.

#### Scenario: Smooth true range for ATR

- **WHEN** ATR is calculated for a positive integer period
- **THEN** the result SHALL use the specified simple rolling mean
- **AND** SHALL NOT use Wilder RMA, EWM, or another smoothing algorithm.

### Requirement: Warmup semantics

For a base-timeframe series with sufficient data, the first ATR output SHALL occur at index `period-1`. Earlier outputs SHALL be JSON null. Validity metadata SHALL report that index as `warmup_bars` and the corresponding bar open time as `valid_from_ms`.

#### Scenario: Report base-timeframe ATR warmup

- **WHEN** a base-timeframe ATR series has sufficient data
- **THEN** outputs before index `period-1` SHALL be `null`
- **AND** validity metadata SHALL identify index `period-1` and its bar open time.

### Requirement: Completed higher-timeframe semantics

For a non-base ATR timeframe, the engine SHALL resample left-closed OHLCV, calculate ATR on HTF bars, shift results by one HTF duration, and forward-fill onto the base grid. Incomplete HTF candles SHALL NOT affect visible output.

#### Scenario: Higher-timeframe ATR bucket is incomplete

- **WHEN** a higher-timeframe ATR bucket has not reached its completion boundary
- **THEN** its value SHALL NOT be visible on the base-timeframe grid
- **AND** the last completed value MAY be forward-filled after its completion boundary.

### Requirement: Shared market read

One indicator plan containing EMA and ATR SHALL load the requested market range once and calculate both features from the same immutable MarketFrame.

#### Scenario: Evaluate EMA and ATR together

- **WHEN** one indicator plan requests EMA and ATR for the same market range
- **THEN** the engine SHALL load the range once
- **AND** SHALL calculate both features from the same immutable MarketFrame.

### Requirement: Golden parity

Automated tests SHALL execute the copied BBB `features/calculations.py` and compare base and HTF ATR output position by position, including null/warmup positions.

#### Scenario: Run the ATR parity suite

- **WHEN** representative base and higher-timeframe ATR fixtures are evaluated
- **THEN** every output and null position SHALL match the copied BBB calculation implementation.
