## ADDED Requirements

### Requirement: Identity twins for partial take nodes

Every partial take distance node SHALL have a resolve twin that yields
its `NodeSpec` without computing it.

- An `atr_partial_take` distance SHALL share the identity of any other
  ATR exit distance over the same ATR column.
- `instance_id` and `fraction_of_initial` SHALL NOT enter any identity.

A successful memoized evaluation of a spec with partial takes SHALL end
with zero `unforeseen_consumptions`.

#### Scenario: Partial takes in a batch

- **WHEN** a batch contains candidates that differ only in a partial
  take's `fraction_of_initial`
- **THEN** every exit distance node SHALL be computed once per batch
- **AND** memoized and non-memoized evaluation SHALL produce
  bit-identical outputs.

### Requirement: No compute regression for specs without partial takes

For specs without partial take rules, the following SHALL be identical
to the evaluation before this change:

- evaluation outputs, including the serialized execution projection,
  `/live-entry`, `/managed-replay` and open-trade outputs;
- memoized compute counts per node family;
- node identities.

#### Scenario: Declared-invariant gate

- **WHEN** the declared-invariant gate runs after this change
- **THEN** every recorded quantity SHALL equal its pre-change value.
