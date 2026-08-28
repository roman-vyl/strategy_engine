## MODIFIED Requirements

### Requirement: Versioned per-bar decision contract

Strategy Engine SHALL expose a versioned decision contract sufficient for
a separate Research Service to execute fills without importing strategy
internals, and sufficient to reproduce the exit-profile-locking and
attribution semantics of the reference (old-monolith) execution model.
The range contract SHALL include strategy and market identity, aligned
range, bar count, and market-data hash.

Entry decisions SHALL be represented as **executable entry
opportunities** — a sparse list of `(bar_index, side)` positions where
`entry_allowed AND protection_ready` both hold, one opportunity per bar
where this is true, not two separate dense or sparse channels for
"entry" and "readiness." `stop_ready`/protection-readiness SHALL NOT be
exposed as its own field or event stream anywhere in this contract — it
is an internal computation that collapses into whether an opportunity
exists.

Each executable entry opportunity SHALL carry a `locked_exit_profile`
value — the exit profile active at that bar, i.e. the value a caller
would lock in if it treats that bar as the real trade entry. Strategy
Engine has no trade-lifecycle state and cannot itself guarantee this
value is honored across a trade's later bars; that is a Research Service
responsibility (see `research-unified-execution-loop-v1`/companion
capability in `research_service`). Each opportunity SHALL also carry
initial stop and initial take information, each as `{ratio, rule_id,
component_id}` — never a bare ratio with no attribution.

Signal-exit information SHALL be represented as **per-side, per-profile
sparse event lists** — a caller holding a locked profile for an open
position looks up only that profile's own event list for bars after
entry, never a flattened current-bar-profile series. Each signal-exit
event SHALL carry one or more candidates, each with `rule_id`,
`component_id`, and `exit_kind` attribution.

When multiple stop rules (or multiple take rules) are applicable at one
entry opportunity and their distances are aggregated into a single
`ratio`, the reported `rule_id`/`component_id` SHALL be selected by a
documented, deterministic rule (including the tied-distance case) —
never left ambiguous or implementation-defined per call.

The response SHALL NOT include a per-bar timestamp array; `bar_index`
together with `market_data_hash` and `bar_count` is the join key back to
Research's own market data. Managed replay SHALL expose explicit
next-bar effective timing.

#### Scenario: Consume Engine decisions in Research Service

- **WHEN** Research Service receives a range evaluation or managed
  replay
- **THEN** it SHALL receive a versioned contract with the identity,
  alignment, provenance, executable entry opportunities (with locked
  exit profile and attributed initial protection), and per-profile
  signal-exit events required for external execution
- **AND** managed decisions SHALL state when they become effective.

#### Scenario: A bar with no executable entry opportunity and no signal-exit event carries no data

- **WHEN** a bar has `entry_allowed AND protection_ready` false for both
  sides, and no profile's signal-exit condition fires
- **THEN** no entry opportunity and no signal-exit event exists for that
  bar in any channel
- **AND** the response size is proportional to the number of bars
  carrying at least one such fact, not the number of bars in the range.

#### Scenario: stop_ready is never a standalone field

- **WHEN** the execution contract is inspected
- **THEN** it contains no `stop_ready` array, field, or event stream of
  its own — protection-readiness is only observable as a component of
  whether an executable entry opportunity exists.

#### Scenario: Every entry opportunity carries a locked-exit-profile candidate value

- **WHEN** an executable entry opportunity is inspected
- **THEN** it carries a `locked_exit_profile` value equal to the exit
  profile active at that opportunity's `bar_index`
- **AND** this value is understood as the candidate lock for a caller
  that treats this bar as the real entry, not as a claim that any
  particular trade actually locked it (Strategy Engine has no
  trade-lifecycle state to make that claim).

#### Scenario: Initial stop/take always carry attribution

- **WHEN** an executable entry opportunity's initial stop or initial
  take is inspected
- **THEN** it is a `{ratio, rule_id, component_id}` triple, never a bare
  ratio
- **AND** no separate per-bar dense ratio series exists elsewhere in the
  response.

#### Scenario: Deterministic attribution under multiple applicable rules

- **WHEN** multiple stop rules or multiple take rules are applicable at
  one entry opportunity and their distances are aggregated into a single
  reported `ratio`
- **THEN** the reported `rule_id`/`component_id` is selected by the same
  deterministic resolution the reference (old-monolith) execution model
  used, including for tied/equal distances
- **AND** this resolution is documented, not left to incidental
  implementation order.

#### Scenario: Signal-exit events are indexed per side and per profile

- **WHEN** signal-exit information is inspected
- **THEN** it is organized as separate event lists per `(side, profile)`
  pair
- **AND** no flattened current-bar-profile `signal_exit[side][bar]`
  series exists in the response
- **AND** each event's candidates carry `rule_id`/`component_id`/
  `exit_kind` attribution.

#### Scenario: Simultaneous long and short on one bar fails loudly

- **WHEN** the Engine's own decision computation would produce both a
  long and a short executable entry opportunity on the same bar
- **THEN** evaluation SHALL fail with an explicit error rather than
  silently emitting one side or an ambiguous opportunity.

#### Scenario: No mandatory timestamp array

- **WHEN** a range evaluation response is inspected
- **THEN** it contains no per-bar timestamp array
- **AND** `bar_index` plus `market_data_hash` plus `bar_count` is
  sufficient for the caller to resolve each bar's timestamp from its own
  market data.

#### Scenario: bar_index indexes exactly the reported range

- **WHEN** any projection element's `bar_index` is inspected
- **THEN** it is a valid zero-based position within `[0, bar_count)` for
  the same `market_data_hash`-identified range the response itself
  reports
- **AND** it corresponds to the same-position candle in a Research
  `MarketFrame` resolved for that identical `market_data_hash`.

### Requirement: Execution facts remain external

Strategy Engine SHALL NOT return executed fills, completed trades, fees,
or PnL. Strategy Engine SHALL compute strategy facts (executable entry
opportunities, protection policy, signal-exit candidates, attribution) —
this is distinct from computing *executed* trading facts and remains
Strategy Engine's role in this architecture.

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

### Requirement: Diagnostic-evaluation entrypoint ownership and provenance

Strategy Engine SHALL own computing diagnostic data on request. A
diagnostic-evaluation request SHALL identify the target the same way an
execution-evaluation request does — strategy identity, market
provenance, and an expected market-data hash. A diagnostic-evaluation
response SHALL carry `config_hash`, `market_data_hash`, and `bar_count`
equal to what the matching execution evaluation for that same request
would produce.

#### Scenario: Diagnostic response provenance matches the execution evaluation it explains

- **WHEN** a diagnostic-evaluation response is returned for a given
  strategy/market/expected-hash request
- **THEN** its `config_hash`, `market_data_hash`, and `bar_count` equal
  those an execution-evaluation response for the identical request would
  report.

#### Scenario: Engine is the sole computer of diagnostic data

- **WHEN** dense per-bar diagnostic data (feature series, context data,
  component evidence, potential-entry traces) exists anywhere in the
  system
- **THEN** it was computed by Strategy Engine's diagnostic-evaluation
  entrypoint, never recomputed or fabricated by Research Service.

### Requirement: This capability does not govern the live entry/open-trade boundary

The historical/batch decision contract this capability defines is
distinct from, and SHALL NOT alter, the live `strategy_engine ↔
strategy_runtime` boundary (`live-entry`, `open-trade` projections and
their `locked_exit_profile`/`DesiredEntry`/`OpenTradeProjectionResult`
shapes). That boundary already implements correct locked-exit-profile
semantics via a caller-held, round-tripped value and is the reference
pattern this capability's historical contract follows — it is read as
prior art, not modified by any requirement in this document.

#### Scenario: Live projection contracts are unaffected

- **WHEN** this capability's historical execution contract changes
- **THEN** `evaluate_live_entry_projection`/`evaluate_open_trade_
  projection` request/response shapes, and the `locked_exit_profile`
  field they carry, are unchanged.

### Requirement: This capability does not govern the public indicator contract

The historical decision contract's internal use of native (non-string-
boxed) indicator computation SHALL NOT alter the public indicator
evaluation contract's normalized-decimal-text serialization
(`ema-indicator-vertical-slice-v1` and sibling vertical-slice
capabilities).

#### Scenario: Public indicator responses remain string-serialized

- **WHEN** the public `/v1/indicator-evaluations/range` endpoint is
  inspected
- **THEN** its `series` values remain normalized-decimal-text strings or
  `null`, unaffected by this capability's internal native computation.
