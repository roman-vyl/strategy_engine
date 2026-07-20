# ATR Distance Indicator Vertical Slice v1 Specification

## ADDED Requirements

### Requirement: Derived ATR dependency

`atr_distance` SHALL derive from exactly one earlier ATR feature in the same plan. The dependency SHALL use the same timeframe and SHALL be resolved by output ID.

#### Scenario: Resolve an ATR-distance dependency

- **WHEN** an `atr_distance` feature is validated
- **THEN** it SHALL reference exactly one earlier ATR output with the same timeframe.

### Requirement: Calculation

For every bar with a valid ATR dependency value, the output SHALL equal `ATR × multiplier`. Null ATR values SHALL remain null. The multiplier SHALL be a positive finite numeric value and booleans SHALL be rejected.

#### Scenario: Multiply a valid ATR series

- **WHEN** an `atr_distance` feature has a positive finite multiplier
- **THEN** every non-null dependency value SHALL be multiplied by it
- **AND** null positions SHALL remain null.

#### Scenario: Reject a non-finite multiplier

- **WHEN** the multiplier is `NaN`, positive infinity, or negative infinity
- **THEN** validation SHALL reject the feature.

### Requirement: No duplicate work

Evaluation SHALL NOT load market data again, calculate ATR again, resample again, or introduce a second warmup. The derived feature SHALL inherit the ATR feature validity metadata.

#### Scenario: Evaluate ATR distance from an existing dependency

- **WHEN** the earlier ATR output is available
- **THEN** the derived feature SHALL reuse its values and validity
- **AND** SHALL NOT trigger another market read, ATR calculation, resample, or warmup.

### Requirement: Compatibility

Caller-owned output IDs, dependency IDs, plan hashing, Decimal-text serialization, range API, and completed HTF ATR semantics SHALL remain unchanged.

#### Scenario: Return ATR distance through the range API

- **WHEN** ATR distance evaluation succeeds
- **THEN** the response SHALL preserve caller IDs, hashing, Decimal-text output, and completed-HTF semantics.
