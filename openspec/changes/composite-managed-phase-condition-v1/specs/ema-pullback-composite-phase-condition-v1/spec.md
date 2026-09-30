## ADDED Requirements

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

#### Scenario: Composite outside a phase rule

- **WHEN** `composite_phase_condition` is used as the `component_id`
  of a `stop_management`, `take_management` or `runtime_exits` rule, or
  of an item in `setups` or `components.blockers`
- **THEN** the spec SHALL be rejected.

### Requirement: Children

A composite phase condition SHALL hold a non-empty list of `children`.
Each child SHALL have a `child_id` and exactly one of:

- `predicate`: a predicate accepted by the predicate layer
  (`pre-entry-predicates-v1`), parsed and evaluated by that layer
  without modification;
- `condition`: `{component_id, params}` where `component_id` is one of
  `bars_in_trade`, `mfe_pct`, `mfe_atr` or `adx_di_threshold`. Its
  params SHALL be exactly that atom's existing params, and its value
  SHALL be computed by that atom's existing formula.

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

#### Scenario: Unsupported atom child

- **WHEN** a child `condition` has `component_id: mfe_r`
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
