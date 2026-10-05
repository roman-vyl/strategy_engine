## MODIFIED Requirements

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

## ADDED Requirements

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
