## MODIFIED Requirements

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
- `thresholds`: the threshold trade `require` children, each a
  `distance_id` with a `trade_metric`, all compared with `>=`;
- `entry_changes`: the `change_since_entry` `require` children, as
  defined in the requirement "Entry-anchored change terms";
- an optional `at_least` with `k` and a list of terms. It SHALL be
  present whenever the path's `at_least` contains at least one trade
  child, whether trade-only or mixed with market children. Each term is
  exactly one of a `condition_id`, a `distance_id` with a
  `trade_metric`, or an `entry_change`. An `at_least` whose children are
  all market SHALL be folded into the path's `condition_id` instead.

A path SHALL be true on a bar iff all of these hold:

- its `condition_id` (if any) is true for the trade side;
- every threshold holds;
- every entry change holds;
- its `at_least` (if any) has at least `k` true terms.

The rule SHALL fire on the first true path in order. Identifiers SHALL
stay opaque: a consumer SHALL NOT need a `component_id`, a child kind
or a strategy parameter.

When a rule has no `paths`, the serialized projection SHALL omit the
field. The projection of a candidate without `composite_phase_condition`
SHALL be byte-identical to that before this change. The serialized path
SHALL omit `entry_changes` when it is empty, and a serialized term SHALL
omit `entry_change` when it is absent.

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

#### Scenario: Composite without entry changes unchanged

- **WHEN** a candidate's composite phase conditions have no
  `change_since_entry` child
- **THEN** its serialized `managed` projection SHALL equal the
  projection produced before this change, byte for byte.

## ADDED Requirements

### Requirement: Entry-anchored change terms

A `change_since_entry` child SHALL be projected as an entry change
`{series_id, op, value}`:

- `series_id` SHALL name a per-bar float series in `distances`: the
  operand's aligned value on every bar of the candidate's range, `NaN`
  (serialized as `null`) where it is missing or non-finite. One series
  SHALL be emitted per child, however many paths reference it.
- `op` SHALL be one of `>=`, `>`, `<=`, `<`; `value` SHALL be the
  child's finite constant.

The consumer SHALL evaluate an entry change for a trade with entry bar
`e` as follows: `anchor = series[e]`, read once per trade; on bar `i`
the term holds iff `series[i]` and `anchor` are both finite and
`series[i] − anchor <op> value`. A consumer that does not support entry
changes SHALL reject a projection that contains one rather than ignore
it.

#### Scenario: Projection shape

- **WHEN** a composite path requires a market predicate and a
  `change_since_entry` child with `op` `>=` and `value` 5
- **THEN** the path SHALL carry a `condition_id` for the predicate and
  one entry change with `op` `>=` and `value` 5
- **AND** its `series_id` SHALL name the operand series in `distances`.

#### Scenario: Entry change inside N-of-M

- **WHEN** a path has `at_least {k: 1, of: [rise, mfe]}` where `rise`
  is `change_since_entry` and `mfe` is `mfe_r`
- **THEN** the `at_least` SHALL carry one `entry_change` term and one
  `distance_id` + `trade_metric` term.

#### Scenario: Agreement with single-trade evaluation

- **WHEN** a trade is replayed through `/managed-replay` and through the
  reference consumer of the projection
- **THEN** both SHALL reach the same phase on the same bar with the
  same `path_id`.
