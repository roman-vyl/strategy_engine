# ADX/DMI Indicator Vertical Slice v1 Specification

## ADDED Requirements

### Requirement: Coupled calculation

ADX, DI+, and DI- SHALL use one shared calculation for each timeframe/period pair and SHALL match the copied BBB implementation bar for bar.

#### Scenario: Evaluate a coupled ADX/DMI group

- **WHEN** one plan requests ADX, DI+, and DI- for the same timeframe and period
- **THEN** the engine SHALL calculate the shared group once
- **AND** each output SHALL match the copied BBB implementation bar for bar.

### Requirement: Validation

Each feature SHALL use kind `adx`, `di_plus`, or `di_minus`, source `close`, one positive integer `period`, and no dependencies or extra parameters.

#### Scenario: Reject an invalid ADX/DMI feature

- **WHEN** a feature has an unsupported kind, invalid source or period, dependency, or extra parameter
- **THEN** validation SHALL reject the feature before evaluation.

### Requirement: Warmup and HTF completion

DI series SHALL preserve BBB's explicit first-`period` null warmup. ADX SHALL preserve the Wilder-over-DX warmup. Higher-timeframe results SHALL become visible on the base grid only after the HTF bucket closes.

#### Scenario: Respect warmup and completed higher-timeframe visibility

- **WHEN** ADX/DMI is evaluated on base or higher-timeframe data
- **THEN** DI and ADX SHALL preserve their BBB warmup boundaries
- **AND** higher-timeframe values SHALL remain hidden until their source bucket closes.

### Requirement: Compatibility

The existing Indicator range API, Decimal-text serialization, deterministic plan hash, and caller-owned output IDs SHALL remain unchanged.

#### Scenario: Return ADX/DMI through the existing range API

- **WHEN** a valid ADX/DMI range evaluation succeeds
- **THEN** values SHALL use normalized decimal text or `null`
- **AND** the response SHALL preserve the deterministic plan hash and caller-owned output IDs.
