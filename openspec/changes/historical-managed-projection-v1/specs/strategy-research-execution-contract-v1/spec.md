## ADDED Requirements

### Requirement: Optional historical managed projection on the execution contract

The per-bar decision contract Strategy Engine exposes to Research
Service MAY include an optional `HistoricalManagedProjection` field,
present only when the evaluated candidate's `exit_management.mode` is
`"managed"`. Its presence and shape SHALL NOT alter the contract's
existing per-bar decision series or evidence fields for candidates that
do not use managed exits.

#### Scenario: Managed candidate contract carries a projection

- **WHEN** Research Service consumes a range evaluation contract for a
  managed candidate
- **THEN** the contract SHALL include a `HistoricalManagedProjection`
  covering the full requested range alongside the existing per-bar
  decision series.

#### Scenario: Non-managed candidate contract is unchanged

- **WHEN** Research Service consumes a range evaluation contract for a
  candidate that does not use managed exits
- **THEN** the contract SHALL NOT include a
  `HistoricalManagedProjection` field, and every other field SHALL be
  unaffected by this capability.

### Requirement: Computational parity for historical managed evaluation

The number of full-range feature evaluations Strategy Engine performs
for a managed candidate SHALL be independent of how many historical
trades that candidate produces. It SHALL be bounded by the distinct
(timeframe, period) indicator keys the candidate's `exit_management`
configuration references, not by trade count.

#### Scenario: Feature evaluation count is trade-count-independent

- **WHEN** the same managed candidate is evaluated against historical
  data producing first 50 trades and then, under a wider date range,
  500 trades
- **THEN** the number of full-range feature evaluations Strategy Engine
  performs for that candidate SHALL NOT scale with the trade count
  difference between the two runs.
