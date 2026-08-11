## MODIFIED Requirements

### Requirement: Honest capability boundaries

Any indicator kind or strategy evaluation with no registered implementation SHALL return `unsupported_capability` rather than fake success.

#### Scenario: Request an unported capability at this slice boundary

- **WHEN** a capability with no registered implementation is requested
- **THEN** the service SHALL return `unsupported_capability`
- **AND** SHALL NOT fabricate a successful result.

### Requirement: Exact range input semantics

The evaluator SHALL calculate from the MarketFrame supplied for the exact requested range. It SHALL NOT silently request earlier warmup bars.

#### Scenario: Evaluate a bounded market frame

- **WHEN** the evaluator receives a MarketFrame for an exact requested range
- **THEN** it SHALL calculate only from that frame
- **AND** SHALL NOT request earlier warmup candles.
