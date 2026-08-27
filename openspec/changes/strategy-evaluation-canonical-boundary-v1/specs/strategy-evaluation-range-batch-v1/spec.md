# Strategy evaluation range-batch v1

## Purpose

Give `POST /v1/strategy-evaluations/range-batch` its first normative
OpenSpec definition: one shared request-level market window, N
candidate variants each carrying only a canonical strategy input and an
ephemeral correlation key, and the shared-market-acquisition-exactly-once
behavior that already exists in the implementation but has never been
protected by a specification.

## ADDED Requirements

### Requirement: One shared market window per batch

A range-batch request SHALL declare exactly one `market` (ticker, base
timeframe, half-open time range) at the request level. Individual
variants SHALL NOT declare their own market, ticker, timeframe, or time
range.

#### Scenario: Variant with its own market is supplied

- **WHEN** a range-batch request variant contains a `market`, `ticker`,
  `timeframe`, `from_ms`, or `to_ms` field
- **THEN** strict HTTP validation SHALL reject the request before any
  market-data acquisition.

### Requirement: Canonical strategy input per variant

Each variant SHALL contain a correlation key and a canonical strategy
input (`strategy_id`, `raw_spec`) as defined by
`strategy-evaluation-canonical-input-v1`. No `strategy_version`,
`instance_id`, `compatibility_profile`, `family`, or `enabled` field
SHALL be required or accepted on a variant.

#### Scenario: Minimal valid variant

- **WHEN** a variant is expressed as `{variant_id, strategy: {strategy_id,
  raw_spec}}`
- **THEN** the batch request accepts it.

### Requirement: Correlation key is ephemeral, not identity

The variant correlation key (`variant_id`) SHALL be used only to match a
request variant to its corresponding response outcome. It SHALL NOT be
read by calculation, SHALL NOT be validated against any strategy or
market identity, and SHALL NOT be treated as a Research run or candidate
identity.

#### Scenario: Duplicate correlation keys

- **WHEN** a range-batch request contains two variants with the same
  `variant_id`
- **THEN** the batch is rejected before any market-data acquisition.

#### Scenario: Correlation key value is caller-defined

- **WHEN** a caller supplies any non-empty string as `variant_id`,
  including a value that is also used elsewhere as a Research
  `candidate_id`
- **THEN** Engine SHALL accept it without interpreting or validating its
  origin.

### Requirement: Shared market-data acquisition exactly once

For a batch of N variants sharing one market window, Engine SHALL
acquire the underlying market dataset (candles/`MarketFrame`) exactly
once for the whole batch, and SHALL reuse that same acquired dataset for
every variant's evaluation. Engine SHALL NOT acquire market data
separately per variant.

#### Scenario: N variants, one acquisition

- **WHEN** a range-batch request with N variants (N > 1) sharing one
  market window is evaluated
- **THEN** the market-data port SHALL be called exactly once for the
  batch
- **AND** all N variant evaluations SHALL be produced from that one
  acquired dataset.

#### Scenario: One variant fails, acquisition is not repeated

- **WHEN** one variant's evaluation raises a typed
  `StrategyEngineError` mid-batch
- **THEN** that variant's outcome SHALL record the error
- **AND** remaining variants SHALL still be evaluated from the same
  already-acquired dataset, without a second acquisition.

### Requirement: Per-variant outcome, no batch-wide short-circuit

The response SHALL report one outcome per requested variant, each
either a successful result or a typed error, preserving request order.
A single variant's evaluation failure SHALL NOT prevent other variants
from being evaluated.

#### Scenario: Mixed success and failure

- **WHEN** one variant in a batch is invalid (e.g. unsupported
  `strategy_id`) and the others are valid
- **THEN** the response SHALL contain N outcomes, in request order,
  with the invalid variant's outcome carrying a typed error and the
  others carrying results.
