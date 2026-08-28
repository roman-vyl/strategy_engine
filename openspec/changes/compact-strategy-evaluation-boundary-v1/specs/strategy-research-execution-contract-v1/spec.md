## MODIFIED Requirements

### Requirement: Versioned per-bar decision contract

Strategy Engine SHALL expose a versioned decision contract sufficient for
a separate Research Service to execute fills without importing strategy
internals. The range contract SHALL include strategy and market
identity, aligned range, bar count, and market-data hash. Per-bar
decisions (entry, signal exit, stop-ready, stop-loss/take-profit ratio)
SHALL be represented as a **sparse sequence of decision events** — one
event per bar that carries at least one decision — not as dense
per-bar arrays covering every bar in the range. The response SHALL NOT
include a per-bar timestamp array; `bar_index` together with
`market_data_hash` and `bar_count` is the join key back to Research's
own market data. Managed replay SHALL expose explicit next-bar effective
timing.

#### Scenario: Consume Engine decisions in Research Service

- **WHEN** Research Service receives a range evaluation or managed
  replay
- **THEN** it SHALL receive a versioned contract with the identity,
  alignment, provenance, and sparse per-bar decision events required for
  external execution
- **AND** managed decisions SHALL state when they become effective.

#### Scenario: A bar with no decision emits no event

- **WHEN** a bar has no entry, no signal exit, and `stop_ready` false
- **THEN** no decision event exists for that bar
- **AND** the response size is proportional to the number of bars
  carrying at least one decision, not the number of bars in the range.

#### Scenario: Stop-loss/take-profit ratio is carried on the entry event only

- **WHEN** a decision event represents an entry
- **THEN** its stop-loss and take-profit ratio values are attached to
  that entry event
- **AND** no separate per-bar ratio series exists elsewhere in the
  response.

#### Scenario: Simultaneous long and short on one bar fails loudly

- **WHEN** the Engine's own decision computation would produce both a
  long and a short entry on the same bar
- **THEN** evaluation SHALL fail with an explicit error rather than
  silently emitting one side or an ambiguous event.

#### Scenario: No mandatory timestamp array

- **WHEN** a range evaluation response is inspected
- **THEN** it contains no per-bar timestamp array
- **AND** `bar_index` plus `market_data_hash` plus `bar_count` is
  sufficient for the caller to resolve each bar's timestamp from its own
  market data.

### Requirement: Execution facts remain external

Strategy Engine SHALL NOT return executed fills, completed trades, fees,
or PnL.

#### Scenario: Inspect an Engine decision response

- **WHEN** Strategy Engine returns entry, exit, stop, take, or managed
  policy decisions
- **THEN** the response SHALL contain no fabricated fill, completed-
  trade, fee, or PnL facts.

## ADDED Requirements

### Requirement: Diagnostic data is not part of the mandatory execution contract

The mandatory range-evaluation response (the decision contract above)
SHALL NOT include dense per-bar feature series, context data, component
evidence, or potential-entry traces. Diagnostic data of this kind is
available only through a separate, explicitly-requested evaluation path,
never as a side effect of an execution-contract request.

#### Scenario: Requesting a range evaluation for execution

- **WHEN** Research Service requests a range evaluation to drive
  execution/accounting
- **THEN** the response contains only the sparse decision contract —
  no `features`, `contexts`, `component_evidence`, or
  `potential_entries` fields.

#### Scenario: Diagnostic data requires an explicit separate request

- **WHEN** dense per-bar diagnostic data is needed for one already-
  evaluated strategy/range/market_data_hash
- **THEN** it is obtained via a distinct diagnostic-evaluation request,
  not embedded in the execution-contract response.
