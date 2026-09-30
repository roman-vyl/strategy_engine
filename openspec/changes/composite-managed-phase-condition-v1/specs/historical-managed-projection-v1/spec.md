## ADDED Requirements

### Requirement: Composite phase transitions are projected as paths

A `phase_transition` rule SHALL carry exactly one of:

- `condition_id`;
- `distance_id` together with `trade_metric`;
- `paths`.

Atomic phase conditions SHALL keep their existing form. The `paths`
variant SHALL be used only for `composite_phase_condition`.

Each path SHALL carry:

- a `path_id`;
- an optional `condition_id`: the AND of all market `require` children,
  and of a market-only `at_least`, as one candidate-wide series per
  side;
- `thresholds`: the trade `require` children, each a `distance_id` with
  a `trade_metric`, all compared with `>=`;
- an optional `at_least` with `k` and a list of terms. It is present
  only when its children mix market and trade kinds. Each term is
  either a `condition_id` or a `distance_id` with a `trade_metric`.

A path SHALL be true on a bar iff all of these hold:

- its `condition_id` (if any) is true for the trade side;
- every threshold holds;
- its `at_least` (if any) has at least `k` true terms.

The rule SHALL fire on the first true path in order. Identifiers SHALL
stay opaque: a consumer SHALL NOT need a `component_id`, a child kind
or a strategy parameter.

When a rule has no `paths`, the serialized projection SHALL omit the
field. The projection of a candidate without `composite_phase_condition`
SHALL be byte-identical to that before this change.

#### Scenario: Market logic stays candidate-wide

- **WHEN** a composite path requires three market children and one
  `mfe_atr` child
- **THEN** the projection SHALL contain one condition series for that
  path and one distance series for the `mfe_atr` child
- **AND** a consumer SHALL resolve the path for any trade with one
  series lookup and one scalar comparison per bar.

#### Scenario: Atomic rule unchanged

- **WHEN** a candidate's phase rules are all atomic
- **THEN** its serialized `managed` projection SHALL equal the
  projection produced before this change, byte for byte.

### Requirement: Path attribution parity

For composite phase conditions, the managed-policy parity between the
candidate-wide projection and single-trade `/managed-replay` SHALL
include the winning `path_id` of every phase transition, in addition to
the transition bar and `rule_id`.

#### Scenario: Reference consumer agrees on path

- **WHEN** the parity corpus evaluates a composite spec for every
  tested side and entry
- **THEN** the reference consumer's (bar, `rule_id`, `path_id`)
  transitions SHALL equal those of `evaluate_managed_replay`.
