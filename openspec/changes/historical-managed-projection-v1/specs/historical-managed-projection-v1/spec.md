## Purpose

Lets Research Service resolve historical managed-policy exits for every
trade in a candidate from one candidate-wide market-semantic projection,
instead of one Strategy Engine call per opened trade, while keeping
strategy semantics owned exclusively by Strategy Engine.

## ADDED Requirements

### Requirement: Candidate-wide managed projection

Strategy Engine SHALL compute, at most once per evaluated candidate,
a `HistoricalManagedProjection` covering the candidate's full requested
market range whenever `exit_management.mode == "managed"`. The
projection SHALL contain: pre-confirm boolean conditions for both trade
sides (`conditions`), fully strategy-parameterized derived distances
with any multiplier or threshold already applied
(`distances`), and an ordered, distilled description of phase
transitions and generic take/stop/exit actions (`rules`). Each entry in
`rules` SHALL be one of exactly four discriminated kinds —
`phase_transition`, `take_action`, `stop_action`, `runtime_exit` — each
carrying only opaque `condition_id`/`distance_id` references, a closed
generic action/exit-class enum (never a raw `component_id` or strategy
parameter), and `confirm_bars`. Every identifier in the projection
(`condition_id`, `distance_id`, `rule_id`) SHALL be opaque to any
consumer — a consumer SHALL NOT need to know the originating
`component_id` or strategy parameter to use the projection correctly,
and SHALL be able to dispatch on `rules[].kind` (and, where present,
the closed `action`/`exit_class` enum) alone.

#### Scenario: Managed candidate receives one projection

- **WHEN** a candidate whose spec sets `exit_management.mode` to
  `"managed"` is evaluated over an aligned market range
- **THEN** Strategy Engine SHALL produce exactly one
  `HistoricalManagedProjection` for that candidate, covering the entire
  requested range
- **AND** the number of full-range feature evaluations performed for
  that candidate SHALL NOT depend on how many trades the candidate
  eventually produces.

#### Scenario: Research dispatches on rule kind alone

- **WHEN** Research Service consumes an entry in `rules`
- **THEN** it SHALL determine what to do using only that entry's
  `kind` and, where present, its closed `action`/`exit_class` enum
- **AND** it SHALL NOT read a `component_id` or any raw strategy
  parameter to make that determination.

#### Scenario: Non-managed candidate is unaffected

- **WHEN** a candidate's spec does not set `exit_management.mode` to
  `"managed"`
- **THEN** no `HistoricalManagedProjection` SHALL be produced or
  required.

### Requirement: Distances are fully parameterized before transport

Every value in `distances` SHALL already have the strategy's own
multiplier and threshold applied by Strategy Engine. A consumer SHALL
NOT need a raw indicator value (e.g. a bare ATR reading) or a strategy
parameter to interpret a distance.

#### Scenario: Stop/target distance is pre-scaled

- **WHEN** a managed candidate's projection includes a distance derived
  from an indicator and a configured multiplier
- **THEN** the transported value SHALL equal `indicator_value *
  multiplier`, not the bare indicator value.

### Requirement: Confirm-bars sustain window is entry-anchored

The confirm-bars sustain window used to promote a pre-confirm condition
to a confirmed signal SHALL be evaluated relative to the real historical
entry index of the specific trade being evaluated, not precomputed as a
single candidate-wide confirmed series. Research Service SHALL apply
this window itself, generically, using the projection's pre-confirm
`conditions` series, the trade's own `entry_index`, and the rule's
`confirm_bars` value.

#### Scenario: Two trades with different entries confirm independently

- **WHEN** two historical trades on the same candidate enter at
  different bar indices and both reference the same `condition_id` with
  the same `confirm_bars`
- **THEN** each trade's confirmation SHALL be computed against its own
  `entry_index`
- **AND** a candidate-wide precomputed confirmed-boolean series SHALL
  NOT be used as the sole source of confirmation.

### Requirement: Managed-policy parity with single-trade managed replay

For any historical trade, evaluating that trade's managed-policy state
via the candidate-wide `HistoricalManagedProjection` plus Research
Service's generic managed lifecycle primitives SHALL produce
managed-policy outputs identical to evaluating the same trade via
`POST /v1/strategy-evaluations/managed-replay`: phase transition
timestamps, active take-profit state timeline, managed stop price
timeline, and runtime-exit trigger bar and rule identity. This
requirement covers only the managed-policy layer (the two evaluators'
outputs/timeline); it does not cover final exit price, the resulting
trade record, or aggregate candidate metrics — those depend on
Research Service's exit arbitration and are validated by a separate
end-to-end Research Service parity check, not by this requirement.

#### Scenario: Parity oracle comparison

- **WHEN** a historical trade is evaluated both via
  `/managed-replay` and via the candidate-wide projection path
- **THEN** the two evaluations SHALL produce identical phase
  transitions, active take-profit timeline, managed stop price
  timeline, and runtime-exit trigger bar/rule for that trade
- **AND** this comparison SHALL NOT itself assert final exit price,
  trade record, or aggregate metrics equality — those are covered by
  the separate end-to-end Research Service parity check.

### Requirement: Historical batch execution does not call managed replay per trade

Research Service's historical managed-policy batch execution path SHALL
NOT issue one Strategy Engine `/managed-replay` HTTP request per opened
trade. It SHALL resolve managed exits for all of a candidate's trades
from that candidate's single `HistoricalManagedProjection`.

#### Scenario: N trades, not N requests

- **WHEN** a managed candidate's historical batch produces N opened
  trades
- **THEN** the number of Strategy Engine requests issued to resolve
  those trades' managed exits SHALL be O(1) per candidate, not O(N).

#### Scenario: Live single-trade replay is unaffected

- **WHEN** a live caller requests managed replay for a single
  already-open trade via `/managed-replay`
- **THEN** that request path SHALL behave exactly as it did before this
  capability existed.
