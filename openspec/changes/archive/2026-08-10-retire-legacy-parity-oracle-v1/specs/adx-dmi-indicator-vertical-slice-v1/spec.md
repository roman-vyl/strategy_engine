## MODIFIED Requirements

### Requirement: Coupled calculation

ADX, DI+, and DI- SHALL use one shared calculation for each timeframe/period pair.

#### Scenario: Evaluate a coupled ADX/DMI group

- **WHEN** one plan requests ADX, DI+, and DI- for the same timeframe and period
- **THEN** the engine SHALL calculate the shared group once.
