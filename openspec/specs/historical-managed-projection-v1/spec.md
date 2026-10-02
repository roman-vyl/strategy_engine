# historical-managed-projection-v1 Specification

## Purpose

Lets Research Service resolve historical managed-policy exits for every
trade in a candidate from one candidate-wide market-semantic projection,
instead of one Strategy Engine call per opened trade, while keeping
strategy semantics owned exclusively by Strategy Engine.
## Requirements
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

### Requirement: Composite phase transitions are projected as paths

A `phase_transition` rule SHALL carry exactly one of:

- `condition_id`;
- `distance_id` together with `trade_metric`;
- `paths`.

Atomic phase conditions SHALL keep their existing form. The `paths`
variant SHALL be used only for `composite_phase_condition`.

Each path SHALL carry:

- a `path_id`;
- an optional `condition_id`: the AND of all market `require` children,
  and of a market-only `at_least`, as one candidate-wide series per
  side;
- `thresholds`: the trade `require` children, each a `distance_id` with
  a `trade_metric`, all compared with `>=`;
- an optional `at_least` with `k` and a list of terms. It SHALL be
  present whenever the path's `at_least` contains at least one trade
  child, whether trade-only or mixed with market children. Each term is
  either a `condition_id` or a `distance_id` with a `trade_metric`. An
  `at_least` whose children are all market SHALL be folded into the
  path's `condition_id` instead.

A path SHALL be true on a bar iff all of these hold:

- its `condition_id` (if any) is true for the trade side;
- every threshold holds;
- its `at_least` (if any) has at least `k` true terms.

The rule SHALL fire on the first true path in order. Identifiers SHALL
stay opaque: a consumer SHALL NOT need a `component_id`, a child kind
or a strategy parameter.

When a rule has no `paths`, the serialized projection SHALL omit the
field. The projection of a candidate without `composite_phase_condition`
SHALL be byte-identical to that before this change.

#### Scenario: Market logic stays candidate-wide

- **WHEN** a composite path requires three market children and one
  `mfe_atr` child
- **THEN** the projection SHALL contain one condition series for that
  path and one distance series for the `mfe_atr` child
- **AND** a consumer SHALL resolve the path for any trade with one
  series lookup and one scalar comparison per bar.

#### Scenario: Trade-only N-of-M is projected

- **WHEN** a composite path has `at_least {k: 2, of: [bars_in_trade,
  mfe_pct, mfe_atr]}`
- **THEN** the path SHALL carry an `at_least` with `k = 2` and three
  `distance_id` + `trade_metric` terms
- **AND** a consumer SHALL resolve it with the same transitions as
  `/managed-replay`.

#### Scenario: Atomic rule unchanged

- **WHEN** a candidate's phase rules are all atomic
- **THEN** its serialized `managed` projection SHALL equal the
  projection produced before this change, byte for byte.

### Requirement: Path attribution parity

For composite phase conditions, the managed-policy parity between the
candidate-wide projection and single-trade `/managed-replay` SHALL
include the winning `path_id` of every phase transition, in addition to
the transition bar and `rule_id`.

#### Scenario: Reference consumer agrees on path

- **WHEN** the parity corpus evaluates a composite spec for every
  tested side and entry
- **THEN** the reference consumer's (bar, `rule_id`, `path_id`)
  transitions SHALL equal those of `evaluate_managed_replay`.

### Requirement: Trade metric `mfe_r`

`TradeMetric` SHALL include `mfe_r`. For an `mfe_r` phase atom, the
projection SHALL emit the rule (or composite trade child) with
`trade_metric: "mfe_r"` and a distance series equal to the atom's R
threshold on every bar.

The consumer SHALL evaluate the metric as
`|mfe_price - entry_price| / initial_risk` with
`initial_risk = |entry_price - initial_stop_price|` of that position,
frozen at entry, and compare it with `>=`. When the position has no
initial stop or its initial risk is not positive, the metric SHALL be
unavailable and the comparison false.

#### Scenario: Projection shape

- **WHEN** a phase rule uses `mfe_r` with `threshold` 6
- **THEN** the rule SHALL carry `trade_metric: "mfe_r"`
- **AND** its distance series SHALL be 6 on every bar.

#### Scenario: Agreement with single-trade evaluation

- **WHEN** a trade has an initial stop
- **THEN** a consumer of the projection SHALL reach the same phase on
  the same bar as the single-trade evaluation.

