## MODIFIED Requirements

### Requirement: Children

A composite phase condition SHALL hold a non-empty list of `children`.
Each child SHALL have a `child_id` and exactly one of:

- `predicate`: a predicate accepted by the predicate layer
  (`pre-entry-predicates-v1`), parsed and evaluated by that layer
  without modification;
- `condition`: `{component_id, params}` where `component_id` is one of
  `bars_in_trade`, `mfe_pct`, `mfe_atr`, `mfe_r` or `adx_di_threshold`. Its
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

#### Scenario: `mfe_r` child

- **WHEN** a child `condition` has `component_id: mfe_r` and a positive
  `threshold`
- **THEN** the spec SHALL be accepted
- **AND** the child SHALL be a trade child, valued by the `mfe_r` atom's
  formula.

#### Scenario: Unsupported atom child

- **WHEN** a child `condition` has a `component_id` outside the list
  above
- **THEN** static validation SHALL reject the spec.
