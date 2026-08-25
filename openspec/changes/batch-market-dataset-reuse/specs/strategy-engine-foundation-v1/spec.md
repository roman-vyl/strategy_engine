## MODIFIED Requirements

### Requirement: Coarse-grained batch API

`POST /v1/strategy-evaluations/range-batch` SHALL represent multiple strategy evaluations sharing one market range.

Variant ordering SHALL be deterministic. Each variant SHALL retain its own identity and success/error envelope.

A batch request SHALL acquire its shared market dataset (the requested `ticker`, `timeframe`, and range) exactly once per batch, as one `MarketFrame`, and every variant in that batch SHALL be evaluated against that exact same acquired `MarketFrame` -- identical bars and identical `MarketFrame.market_data_hash` -- rather than each variant independently acquiring its own copy. When `market_data_hash` is exposed by existing output options, the exposed value SHALL be identical across all variants in the batch. This requirement does not add or change any response field, and does not require `market_data_hash` to be present when existing output options omit it. This guarantee covers only the shared market dataset (L0); the foundation need not implement reuse of any calculation derived from strategy-level parameters (indicators, contexts, setups, triggers, entries, exits, or any other per-variant computation).

#### Scenario: Batch contains multiple variants

- **WHEN** a range-batch request contains multiple ordered variants
- **THEN** the response SHALL preserve their order and identities
- **AND** each variant SHALL have its own result or error envelope.

#### Scenario: Variants in one batch share one market dataset

- **WHEN** a range-batch request contains two or more variants
- **THEN** the market dataset for the requested `ticker`, `timeframe`, and range SHALL be acquired exactly once for that batch, as one `MarketFrame`
- **AND** every variant SHALL be evaluated against that exact same acquired `MarketFrame`
- **AND** when `market_data_hash` is exposed by existing output options, its value SHALL be identical across all variants
- **AND** a failure to acquire the shared market dataset SHALL fail the entire batch rather than being retried independently per variant.
