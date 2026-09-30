# ema-pullback-composite-setup-v1 Specification

## Purpose
Let one EMA Pullback setup express alternative combinations of
pre-entry conditions. Its children are predicates over canonical
features/context and existing semantic setups, combined by AND within
a path, N-of-M within a path, and OR across paths.

## Requirements

### Requirement: Ordinary setup at the outer boundary

`composite_setup` SHALL be a setup component:

- it SHALL produce an ordinary `SetupMask` with local, context-gated
  and final masks;
- it MAY declare its own `context_consumption`, applied after the local
  composite mask exactly as for any other setup;
- its final mask SHALL be AND-composed with the other declared setups
  by the existing setup composition.

`evaluate_setups` SHALL NOT treat it differently from other setups
beyond dispatching on its `component_id`.

#### Scenario: Composite alongside other setups

- **WHEN** a spec declares `untouched_anchor_setup` and a
  `composite_setup`
- **THEN** `setups_ok` SHALL equal the AND of both final masks, as for
  any two setups.

### Requirement: Children

`params.children` SHALL be a non-empty list. Each child SHALL have:

- a `child_id` unique within the composite and not containing `/`;
- exactly one of `predicate` or `setup`.

For a `setup` child:

- its `component_id` SHALL be one of `untouched_anchor_setup`,
  `ema_bounce_counter_setup`, `anchor_stack_width_setup`;
- it SHALL NOT carry `instance_id` or `context_consumption`.

`composite_setup` SHALL NOT be a child.

#### Scenario: Nested gate is rejected

- **WHEN** a setup child declares `context_consumption`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Nested composite is rejected

- **WHEN** a setup child has `component_id` `composite_setup`
- **THEN** static validation SHALL reject the spec.

### Requirement: Semantic setup children are reused unchanged

A setup child SHALL be evaluated by the existing implementation of its
component. It SHALL use the same parameters, defaults, columns and
trace, and SHALL contribute its local setup mask. No context gate
SHALL be applied to it. Its identity SHALL be the existing local setup
identity.

#### Scenario: Width child equals the width setup

- **WHEN** a composite has a single path requiring a single
  `anchor_stack_width_setup` child
- **THEN** the composite local mask SHALL equal the local mask of the
  same `anchor_stack_width_setup` declared directly.

### Requirement: Paths

`params.paths` SHALL be a non-empty list. Each path SHALL have:

- a unique `path_id` not containing `/`;
- at least one of a non-empty `require` list or an `at_least`
  object `{k, of}`, where `of` is a non-empty list without duplicates
  and `1 ≤ k ≤ len(of)`.

Every referenced `child_id` SHALL exist, and every child SHALL be
referenced by at least one path.

A path mask SHALL equal the AND of its `require` children AND (the
number of True `of` children ≥ k). The composite local mask SHALL
equal the OR of its path masks.

#### Scenario: Two alternative paths

- **WHEN** path `developed` requires [width8, adx1h_25] and path
  `alternate` requires [width10] with at_least {k: 2, of: [adx1h_20,
  adx5m_25, rsi_range]}
- **THEN** the composite local mask SHALL be True exactly on bars where
  either path mask is True.

#### Scenario: Unreferenced child is rejected

- **WHEN** a child is not referenced by any path
- **THEN** static validation SHALL reject the spec.

### Requirement: Evidence

The composite `SetupMask.trace` SHALL contain:

- `child:<child_id>` masks;
- `path:<path_id>` masks;
- `path:<path_id>:at_least_count` series for paths with `at_least`;
- `winning_path`: the first True path in declared order, or null.

#### Scenario: Inspect which path admitted a bar

- **WHEN** both paths are True on a bar
- **THEN** `winning_path` on that bar SHALL be the path declared first.

### Requirement: Compute cost

A composite SHALL add no computation other than:

- the features and semantic setups its children reference;
- vectorized mask operations linear in the number of bars per child
  and per path.

Identical children, by identity, SHALL be computed once per
evaluation context.

#### Scenario: Child shared by two paths

- **WHEN** the same child is referenced by two paths
- **THEN** it SHALL be computed once.
