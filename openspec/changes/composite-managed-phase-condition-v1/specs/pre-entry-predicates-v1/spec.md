## MODIFIED Requirements

### Requirement: Predicate is an internal layer, not a strategy role

`PreEntryPredicate` SHALL be an internal evaluation contract. It SHALL
NOT be a strategy role or component:

- it SHALL NOT appear in any `*_SUPPORTED` allowlist;
- it SHALL NOT be accepted as a top-level item of `setups`,
  `components.blockers`, `direction`, `trigger`, exits, or managed
  phase rules.

Its only consumers SHALL be `composite_setup` and, as a child of a
managed phase condition, `composite_phase_condition`
(`ema-pullback-composite-phase-condition-v1`). Both consumers SHALL
use the same parse, evaluation and identity functions. Neither SHALL
wrap, re-parse or re-implement a predicate.

#### Scenario: Predicate at top level is rejected

- **WHEN** a spec places a predicate object directly in `setups` or
  `components.blockers`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Predicate as a bare phase condition is rejected

- **WHEN** a `phase_rules` entry has a predicate object as its
  `condition`, not wrapped in a `composite_phase_condition`
- **THEN** the spec SHALL be rejected.

#### Scenario: Predicate inside a composite phase condition

- **WHEN** a `composite_phase_condition` child carries a predicate
- **THEN** it SHALL be parsed by `parse_predicate`, evaluated by
  `evaluate_predicate` and identified by `resolve_predicate`, exactly
  as a `composite_setup` child.
