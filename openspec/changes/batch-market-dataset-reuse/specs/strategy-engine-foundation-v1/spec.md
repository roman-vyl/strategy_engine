## MODIFIED Requirements

### Requirement: Coarse-grained batch API

`POST /v1/strategy-evaluations/range-batch` SHALL represent multiple strategy evaluations sharing one market range.

Variant ordering SHALL be deterministic. Each variant SHALL retain its own identity and success/error envelope.

A batch request SHALL load its shared market dataset (the requested `ticker`, `timeframe`, and range) exactly once per batch, and every variant in that batch SHALL be evaluated against that same market dataset -- identical bars and identical `market_data_hash` -- rather than each variant independently acquiring its own copy. This guarantee covers only the shared market dataset (L0); the foundation need not implement reuse of any calculation derived from strategy-level parameters (indicators, contexts, setups, triggers, entries, exits, or any other per-variant computation).

#### Scenario: Batch contains multiple variants

- **WHEN** a range-batch request contains multiple ordered variants
- **THEN** the response SHALL preserve their order and identities
- **AND** each variant SHALL have its own result or error envelope.

#### Scenario: Variants in one batch share one market dataset

- **WHEN** a range-batch request contains two or more variants
- **THEN** the market dataset for the requested `ticker`, `timeframe`, and range SHALL be acquired exactly once for that batch
- **AND** every variant's result SHALL reflect the same `market_data_hash` and the same underlying bars
- **AND** a failure to acquire the market dataset SHALL fail the entire batch rather than being retried independently per variant.
