## ADDED Requirements

### Requirement: Memoized predicate children in the managed projection

When the historical projection is built under an evaluation context,
every predicate child of a composite phase condition SHALL be evaluated
through its predicate identity. It SHALL therefore share memoized nodes
with identical predicates of `composite_setup`, of other rules and of
other batch candidates.

The batch pre-pass SHALL predict these consumptions with the same
resolution the projection uses: a `managed` stage, resolved after the
exit-policy stage, that lists for every composite phase rule in
declared order, for `long` then `short`, each predicate child's `local`
node followed by its `nested` nodes. The stage SHALL be empty unless
`exit_management.mode` is `managed` and some composite phase condition
has a predicate child; for every other spec the pre-pass predictions
SHALL be unchanged and the projection SHALL resolve no identities. When
the stage cannot be resolved it SHALL be absent and the projection
SHALL evaluate its predicate children unmemoized. A successful memoized
evaluation of a spec with a composite phase condition SHALL end with
zero `unforeseen_consumptions`.

The following SHALL NOT be memo nodes:

- path folding;
- `at_least` counting;
- the `adx_di_threshold` series.

#### Scenario: Batch differing only in the MFE threshold

- **WHEN** a batch contains candidates whose composite phase conditions
  differ only in an `mfe_atr` threshold
- **THEN** each predicate child mask SHALL be computed once per batch
- **AND** memoized and non-memoized evaluation SHALL produce identical
  projections.

### Requirement: No compute regression for existing managed specs

For specs without `composite_phase_condition`, the following SHALL be
identical to the evaluation before this change:

- evaluation outputs, including the serialized managed projection;
- memoized compute counts per node family;
- node identities;
- `/managed-replay` and live open-trade outputs.

#### Scenario: Declared-invariant gate with managed cases

- **WHEN** the declared-invariant gate runs its managed cases after
  this change
- **THEN** every recorded quantity SHALL equal its pre-change value.
