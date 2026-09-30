## ADDED Requirements

### Requirement: Single-trade replay evaluates composite phase conditions

The single-trade managed evaluator SHALL evaluate
`composite_phase_condition` (`ema-pullback-composite-phase-condition-v1`)
in both of its entry points:

- `POST /v1/strategy-evaluations/managed-replay`;
- the live start-after-entry projection.

It SHALL build the market part of every path once per call from the
shared fold of market children. On each bar it SHALL check trade
children with the existing atom formulas. It SHALL NOT evaluate market
children per bar through a separate code path.

For specs without `composite_phase_condition`, replay events, per-bar
decisions and final state SHALL be identical to those before this
change.

#### Scenario: Composite through managed-replay

- **WHEN** Research calls `/managed-replay` for a trade of a spec whose
  phase rule uses `composite_phase_condition`
- **THEN** the replay SHALL succeed
- **AND** the `phase_changed` events SHALL carry `component_id:
  composite_phase_condition` and the winning `path_id` in `metadata`.

#### Scenario: Existing managed spec unchanged

- **WHEN** a managed spec uses only atomic phase conditions
- **THEN** its `/managed-replay` and live open-trade outputs SHALL be
  identical to the outputs before this change.

### Requirement: Context bundle for state predicates in managed evaluation

When a composite phase condition contains a `state` predicate, directly
or inside `temporal`, the managed evaluators SHALL obtain HTF state from
the `ContextBundle` of the same frame:

- live open-trade and the historical projection SHALL use the bundle
  already built by the strategy evaluation;
- `/managed-replay` SHALL build the bundle only when such a predicate
  is present.

For all other specs, `/managed-replay` SHALL NOT build a bundle.

#### Scenario: No state predicate, no extra work

- **WHEN** `/managed-replay` evaluates a spec with no `state` predicate
  in any composite phase condition
- **THEN** no context bundle SHALL be built for the replay.
