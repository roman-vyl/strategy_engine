# ema-pullback-composite-phase-condition-v1 Specification

## Purpose
`composite_phase_condition`: a managed phase condition that combines
existing pre-entry predicates and the existing managed trade atoms by
named paths (AND, N-of-M, OR), evaluated identically by single-trade
replay, live open-trade and the candidate-wide historical projection.
## Requirements
### Requirement: Ordinary phase condition at the outer boundary

`composite_phase_condition` SHALL be accepted only as the `condition`
of an `exit_management.phase_rules` entry. From the outside it SHALL
behave as any other phase condition. The following SHALL NOT change:

- phases and their ranks;
- rule order and the skip of rules whose target rank is not above the
  current phase;
- the same-bar cascade;
- `activate_when` and the stop, take and runtime actions;
- the historical (offset 0) and live (offset 1) start semantics.

#### Scenario: Composite in a phase rule

- **WHEN** a managed spec has a phase rule to `proven` whose condition
  is a `composite_phase_condition`
- **AND** on some bar one of its paths is true
- **THEN** the trade SHALL move to `proven` on that bar
- **AND** later rules of the same bar SHALL be checked against the new
  phase, exactly as for an atomic condition.

#### Scenario: Composite as a setup or blocker

- **WHEN** `composite_phase_condition` is used as the `component_id`
  of an item in `setups` or `components.blockers`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Composite as a stop, take or runtime rule

- **WHEN** `composite_phase_condition` is used as the `component_id`
  of a `stop_management`, `take_management` or `runtime_exits` rule
- **THEN** it SHALL be rejected exactly as any unsupported component of
  that list is today: the historical projection and the live history
  planner fail closed on it up front, and single-trade replay fails
  closed when the rule's activation phase is reached
- **AND** static validation of those lists SHALL be unchanged by this
  capability.

### Requirement: Children

A composite phase condition SHALL hold a non-empty list of `children`.
Each child SHALL have a `child_id` and exactly one of:

- `predicate`: a predicate accepted by the predicate layer
  (`pre-entry-predicates-v1`), parsed and evaluated by that layer
  without modification;
- `condition`: `{component_id, params}` where `component_id` is one of
  `bars_in_trade`, `mfe_pct`, `mfe_atr`, `mfe_r`, `adx_di_threshold` or
  `change_since_entry`. For the existing atoms, its params SHALL be
  exactly that atom's existing params, and its value SHALL be computed
  by that atom's existing formula. `change_since_entry` SHALL follow the
  requirement "Entry-anchored change child".

The following SHALL be rejected:

- a nested `composite_phase_condition`;
- a `setup` child or any blocker;
- any other `component_id`;
- a child with both or neither of `predicate` and `condition`;
- unknown fields.

#### Scenario: Owner's case

- **WHEN** children are `adx5` (ADX base > 35), `adx1h` (ADX 1h > 25),
  `di1h` (DI+ 1h > DI− 1h with a `short` override swapping the
  operands) and `mfe` (`mfe_atr`)
- **AND** paths are `fast: [adx5, mfe]` and `htf: [adx1h, di1h, mfe]`
- **THEN** the spec SHALL be accepted
- **AND** the condition SHALL be true exactly when `(adx5 AND mfe) OR
  (adx1h AND di1h AND mfe)`.

#### Scenario: `mfe_r` child

- **WHEN** a child `condition` has `component_id: mfe_r` and a positive
  `threshold`
- **THEN** the spec SHALL be accepted
- **AND** the child SHALL be a trade child, valued by the `mfe_r` atom's
  formula.

#### Scenario: `change_since_entry` child

- **WHEN** a child `condition` has `component_id: change_since_entry`
  with a feature `operand`, `op` `>=` and a finite `value`
- **THEN** the spec SHALL be accepted
- **AND** the child SHALL be a trade child.

#### Scenario: Unsupported atom child

- **WHEN** a child `condition` has a `component_id` outside the list
  above
- **THEN** static validation SHALL reject the spec.

### Requirement: Paths

A composite phase condition SHALL hold a non-empty list of `paths`.
Each path SHALL have a `path_id` and at least one of:

- `require`: a list of child ids that must all be true;
- `at_least: {k, of}`: at least `k` of the listed child ids true, with
  `1 ≤ k ≤ len(of)`.

A path SHALL be true on a bar iff every `require` child is true and,
when `at_least` is present, at least `k` of its `of` children are true.
`require` and `at_least.of` MAY mix market (predicate,
`adx_di_threshold`) and trade (`mfe_atr`, `mfe_pct`, `bars_in_trade`)
children.

The condition SHALL be true iff some path is true. When several paths
are true, the first in declared order SHALL be the winning path.

The following SHALL be validated as for `composite_setup`:

- unique `child_id` and `path_id`;
- no `/` in ids;
- no unknown or repeated references within one list;
- every child referenced by at least one path.

#### Scenario: Mixed N-of-M

- **WHEN** a path has `require: [bars]` and `at_least: {k: 2, of:
  [adx5, mfe, adxdi]}` where `adx5` is a predicate, `mfe` is `mfe_atr`
  and `adxdi` is `adx_di_threshold`
- **THEN** the path SHALL be true on a bar iff `bars` is true and at
  least two of the three are true on that bar.

#### Scenario: Trade-only N-of-M

- **WHEN** a path has `at_least: {k: 2, of: [bars, pct, atr]}` where
  the children are `bars_in_trade`, `mfe_pct` and `mfe_atr`
- **THEN** the path SHALL be true on a bar iff at least two of the
  three are true on that bar, in single-trade replay and in the
  projection alike.

#### Scenario: Unreferenced child

- **WHEN** a child is not referenced by any path
- **THEN** static validation SHALL reject the spec.

### Requirement: Side and readiness

A composite phase condition SHALL be evaluated for the trade's side.

- Predicate children SHALL follow the predicate layer's side semantics:
  side-free unless a `short` override is given.
- `adx_di_threshold` SHALL keep its existing side-relative DI
  alignment.

Any child that is not ready or non-finite on a bar SHALL be false on
that bar:

- a predicate on a non-finite operand;
- `mfe_atr` with a missing or non-positive ATR;
- `adx_di_threshold` with a missing value.

There SHALL be no negation, so a not-ready child can never make a path
true.

Temporal predicate windows SHALL be market-time windows. They MAY
include bars before the entry.

#### Scenario: Warm-up before a transition

- **WHEN** the 1h ADX column is not yet valid on a bar
- **THEN** every path requiring `adx1h` SHALL be false on that bar.

### Requirement: No second market-condition language

The market value of a predicate child SHALL be the mask produced by
`evaluate_predicate` for the trade side. The market value of an
`adx_di_threshold` child SHALL be produced by the same formula as the
atomic `adx_di_threshold` rule. Managed SHALL NOT define its own
predicate type, operand grammar, feature dispatch or indicator
computation.

#### Scenario: Same predicate pre-entry and post-entry

- **WHEN** the same ADX 1h predicate appears in a `composite_setup`
  and in a composite phase condition of one spec
- **THEN** both SHALL read the same plan column through the predicate
  layer
- **AND** that feature SHALL be computed once for the evaluation.

### Requirement: Path attribution

A `phase_changed` event produced by a composite phase condition SHALL
carry:

- `component_id` = `composite_phase_condition`;
- `metadata.path_id` = the winning path;
- `metadata.children` = the boolean value, on the transition bar, of
  every child referenced by the winning path.

#### Scenario: Attribution of the second path

- **WHEN** on the transition bar path `fast` is false and path `htf`
  is true
- **THEN** the event SHALL carry `path_id: htf`.

### Requirement: One composite evaluation across execution paths

The single-trade replay (`/managed-replay`), the live start-after-entry
projection and the historical projection SHALL derive the market part
of every path from one shared fold of market children. Trade children
SHALL be evaluated by the existing atom formulas: `_phase_met` in
single-trade replay, and distances with the matching `trade_metric` in
the projection.

#### Scenario: Equivalence on the parity corpus

- **WHEN** a composite spec is evaluated for any trade both through
  `/managed-replay` and through the candidate-wide projection with the
  reference consumer
- **THEN** the sequence of phase transitions SHALL be identical,
  including bar, `rule_id` and `path_id`.

### Requirement: Entry-anchored change child

`change_since_entry {operand, op, value}` SHALL be a trade child of a
composite phase condition.

- `operand` SHALL be a feature reference in the predicate layer's
  operand grammar, resolved through the canonical feature-kind
  contract. A price or constant operand SHALL be rejected.
- `op` SHALL be one of `>=`, `>`, `<=`, `<`. `value` SHALL be a finite
  number of any sign.
- Unknown fields, `lookback` and `short` SHALL be rejected.

For a trade with entry bar `e`, on a bar `i ≥ e` the child SHALL be
True iff `operand(i) − operand(e) <op> value`, where `operand(x)` is the
operand's aligned value on base bar `x`. For an operand on a higher
timeframe, `operand(x)` SHALL be the value of its last completed bar at
`x`, with no look-ahead, exactly as the predicate layer reads it.

- The anchor `operand(e)` SHALL be fixed for the life of the trade.
- The child SHALL be False on a bar where `operand(i)` or `operand(e)`
  is missing or non-finite.
- The child SHALL be side-free: the same `op` and `value` apply to both
  sides.
- The historical start (offset 0) and the live start (offset 1) SHALL
  use the same anchor `operand(e)`.

`change_since_entry` SHALL be accepted only as a child `condition` of
`composite_phase_condition`. As the `condition` of a phase rule, or
anywhere else, it SHALL be rejected.

#### Scenario: Rise from the entry value

- **WHEN** a child is `change_since_entry` on `rsi` (`base`, 14) with
  `op` `>=` and `value` 5
- **AND** the operand is 21 on the entry bar and 26 three bars later
- **THEN** the child SHALL be True on that later bar
- **AND** it SHALL be False on every earlier bar of the trade where the
  operand is below 26.

#### Scenario: Higher-timeframe operand

- **WHEN** the operand is on `4h` with a `5m` base timeframe
- **THEN** the anchor SHALL be the last completed `4h` value at the
  entry bar
- **AND** the difference SHALL change only on base bars where a new
  `4h` bar has completed.

#### Scenario: Entry bar

- **WHEN** `op` is `>=` and `value` is 0
- **AND** the operand is finite on the entry bar
- **THEN** the child SHALL be True on the entry bar.

#### Scenario: Anchor not ready

- **WHEN** the operand is not finite on the entry bar
- **THEN** the child SHALL be False on every bar of that trade.

#### Scenario: Side-relative rise

- **WHEN** a path requires `change_since_entry` on feature `A`
  (`4h`) `>=` 5 and a `compare` predicate feature `B` (`4h`) `>`
  feature `C` (`4h`) with a `short` override swapping the operands
- **THEN** for a long trade the path SHALL be true where the rise holds
  and `B` is above `C`
- **AND** for a short trade where the rise holds and `C` is above `B`.

#### Scenario: Placement outside a composite

- **WHEN** a phase rule has `condition.component_id:
  change_since_entry`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Agreement across execution paths

- **WHEN** a spec with a `change_since_entry` child is evaluated for any
  trade through single-trade evaluation and through the historical
  projection with the reference consumer
- **THEN** the phase transitions SHALL be identical, including bar,
  `rule_id` and `path_id`.

