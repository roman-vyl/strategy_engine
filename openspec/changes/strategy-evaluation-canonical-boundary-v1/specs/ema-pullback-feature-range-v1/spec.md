## MODIFIED Requirements

### Requirement: Coarse-grained strategy request

`POST /v1/strategy-evaluations/range` SHALL accept the canonical
strategy input (`strategy-evaluation-canonical-input-v1`), canonical
ticker, base timeframe, and aligned half-open range. The caller SHALL
NOT provide an IndicatorPlan or precomputed features, and SHALL NOT
provide `strategy_version`, `instance_id`, or `compatibility_profile`.

#### Scenario: Request an EMA Pullback range evaluation

- **WHEN** a caller submits a canonical strategy input and aligned
  market range
- **THEN** the service SHALL evaluate the range without requiring an
  `IndicatorPlan` or precomputed features.

#### Scenario: Legacy envelope field is supplied

- **WHEN** a range request's `strategy` object contains
  `strategy_version`, `instance_id`, or `compatibility_profile`
- **THEN** strict HTTP validation SHALL reject the request before
  evaluation begins.

### Requirement: Internal feature discovery

For `strategy_id=ema_pullback`, the service SHALL build the
authoritative feature plan from `raw_spec` unconditionally — no
`compatibility_profile` or equivalent selector gates this behavior.

#### Scenario: Discover features for an EMA Pullback strategy

- **WHEN** an EMA Pullback range request is accepted
- **THEN** the service SHALL build its authoritative feature plan from
  `raw_spec` alone.
