## ADDED Requirements

### Requirement: Composite phase condition features use the canonical plan

Planning SHALL recurse into `composite_phase_condition` children:

- feature references of predicate children SHALL be planned as ordinary
  `PlannedFeature` entries, through the same canonical feature-kind
  contract, the same `add()` and the same fail-closed label-collision
  check as `composite_setup` predicate features;
- atom children SHALL be planned by the existing atom planning: ATR for
  `mfe_atr`, ADX/DMI for `adx_di_threshold`.

For a spec without `composite_phase_condition`, the plan (features,
order and `plan_hash`) SHALL be unchanged.

#### Scenario: Shared ADX column

- **WHEN** a composite phase condition predicate requests `adx` on `1h`
  with period 14
- **AND** a `composite_setup` predicate requests the same feature
- **THEN** the plan SHALL contain one `adx` feature for (`1h`, 14).

#### Scenario: Plan unchanged without composite phase condition

- **WHEN** a managed spec has only atomic phase conditions
- **THEN** its `plan_hash` SHALL equal the `plan_hash` produced before
  this change.
