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
`initial_stop` and `initial_take`, each `{ratio, attribution:
ExitAttribution} | null` — see "Attribution shape" below for
`ExitAttribution` and "Initial stop/take optionality" for the
nullability rule. A non-null leg is never a bare ratio with no
attribution.

Signal-exit information SHALL be represented as **per-side, per-profile
sparse event lists** — a caller holding a locked profile for an open
position looks up only that profile's own event list for bars after
entry, never a flattened current-bar-profile series. Each signal-exit
event SHALL carry one or more candidates, each `{attribution:
ExitAttribution}`.

### Attribution shape (shared across all historical execution facts)

```
ExitAttribution
  rule_id
  component_id
  exit_kind
```

Every `ExitAttribution` instance on the wire is populated in full —
`rule_id`/`component_id` are never null on an attribution object that
exists (a leg or candidate either has a rule that produced it, in which
case its attribution is fully populated, or the leg/candidate does not
exist at all — see "Initial stop/take optionality"). Canonical
`exit_kind` values, fixed by this capability, not left to per-caller
convention: `initial_stop → "stop_loss"`, `initial_take →
"take_profit"`, signal-exit candidate → `"signal"`.

`ExitAttribution` does **not** carry a `layer` field on the wire —
`layer` is a canonical derived constant (`"exit_policy"` for every
historical execution fact governed by this capability), not an
independent per-fact Engine decision. Research Service SHALL derive
`layer = "exit_policy"` for these facts rather than read it from the
wire or decide it independently (see companion `research_service`
capability for the consuming side of this rule).

### Multi-rule attribution algorithm (normative, old-BBB-compatible)

When multiple stop rules (or multiple take rules) are applicable at one
entry opportunity, the single reported `ratio`/`ExitAttribution` for
that leg SHALL be selected by this exact procedure, matching the
reference (old-monolith) execution model's `_compile_distance_series`/
`_pick_distance_instance` resolution verbatim (`exits.py:152-179`,
`exit_attribution.py:155-178`):

1. Collect every applicable rule's `(rule identity, distance)` pair for
   that leg (stop or take, independently), in the strategy config's
   declared rule order: `always_on` exits list order first, then the
   active profile's own exits list order — never re-sorted at any
   stage, for either leg.
2. The aggregate distance for that leg is `min()` over every applicable
   rule's distance — **`min()` is used for both stop and take legs
   identically**; there is no separate "tightest for stop, most
   favorable for take" direction. (This corrects an earlier, incorrect
   assumption in this document's history that the two legs might use
   different aggregation directions.)
3. **Attribution owner**: scan the same declared-order list from step 1
   and select the **first** rule (by that same declared order) whose
   own individual distance equals the aggregate `min()` value from step
   2 (equality within a small numerical epsilon, matching the reference
   model's own tolerance, to account for floating-point noise — not an
   exact-bitwise-equality requirement).
4. **On an exact tie** (two or more rules' distances equal the
   aggregate): step 3 already resolves this — "first in declared order
   among values equal to the minimum" inherently selects the earliest-
   declared rule on a tie. No separate tie-break rule exists beyond
   declared-order-first; this is explicit in the reference model
   (`_pick_distance_instance`'s own docstring: "first in spec on tie"),
   not an incidental side effect of iteration order.
5. The winning rule's identity becomes the leg's
   `ExitAttribution.rule_id`/`component_id`. (The reference model's own
   `rule_id`/`component_id` split maps directly to this contract's
   `ExitAttribution.rule_id`/`component_id` — same two identifiers, no
   remapping.)

This is binding on the I1 builder implementation, not a hint — an I1
implementer SHALL NOT choose a different aggregation direction or
tie-break without an explicit follow-up OpenSpec change.

### Initial stop/take optionality (normative)

`initial_stop` and `initial_take` are **independently nullable** —
matching the reference model exactly (`exits.py::_stop_ready`: a rule
group's readiness check only constrains on a leg if that group has at
least one rule for that leg at all; a group with zero configured stop
rules never blocks readiness on the stop leg, and symmetrically for
take). A strategy configuration MAY have take-only or stop-only exit
rules for a given `always_on`+profile combination; `protection_ready`
(and therefore whether an executable entry opportunity exists) requires
only that whichever leg(s) **are** configured are computable (not
NaN/undefined from warmup) at that bar — it does NOT require both legs
to be configured.

`initial_stop: {ratio, attribution: ExitAttribution} | null` and
`initial_take: {ratio, attribution: ExitAttribution} | null` — `null`
means "no stop (or take) rule is configured/applicable for this
opportunity's active profile combination," not an error or an
unresolved value. A non-null leg is always fully populated (`ratio` and
a complete `ExitAttribution`) — there is no partially-populated leg
(e.g. a ratio with a null `rule_id`).

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

#### Scenario: A non-null initial stop/take always carries full attribution

- **WHEN** an executable entry opportunity's initial stop or initial
  take is non-null
- **THEN** it is a `{ratio, attribution: ExitAttribution}` pair with a
  fully-populated `ExitAttribution` (`rule_id`, `component_id`,
  `exit_kind`) — never a bare ratio, never a partially-populated
  attribution
- **AND** no separate per-bar dense ratio series exists elsewhere in the
  response.

#### Scenario: A leg with no applicable rule is null, not a fabricated value

- **WHEN** a strategy configuration has no stop rule (or no take rule)
  applicable to an entry opportunity's active `always_on`+locked-profile
  combination
- **THEN** the corresponding `initial_stop` (or `initial_take`) is
  `null`
- **AND** this alone does not prevent the entry opportunity from
  existing, provided `protection_ready` holds for whichever leg(s) are
  actually configured.

#### Scenario: Aggregation uses min() identically for stop and take legs

- **WHEN** multiple stop rules, or multiple take rules, are applicable
  at one entry opportunity
- **THEN** the reported `ratio` for that leg is the minimum distance
  across all applicable rules for that leg — the same `min()` rule for
  both stop and take, no separate "tightest"/"most favorable" direction
  per leg.

#### Scenario: Attribution owner is the first-declared rule matching the aggregate value

- **WHEN** the aggregate `ratio` for a leg is computed
- **THEN** the reported `ExitAttribution` identifies whichever
  applicable rule's own individual distance equals that aggregate value
  and appears first in the strategy config's declared rule order
  (`always_on` exits list, then the active profile's own exits list,
  never re-sorted)
- **AND**, on an exact tie between two or more rules' distances, the
  same first-in-declared-order selection resolves it — no separate
  tie-break exists.

#### Scenario: Signal-exit events are indexed per side and per profile

- **WHEN** signal-exit information is inspected
- **THEN** it is organized as separate event lists per `(side, profile)`
  pair
- **AND** no flattened current-bar-profile `signal_exit[side][bar]`
  series exists in the response
- **AND** each event's candidates carry a fully-populated
  `ExitAttribution` (`rule_id`/`component_id`/`exit_kind`).

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
