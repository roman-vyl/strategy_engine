## MODIFIED Requirements

### Requirement: Supported predicate classes

The layer SHALL support exactly the following classes:

- `compare {left, op, right}` with `op` in `>`, `>=`, `<`, `<=`.
  - Each operand SHALL be a feature reference, an episode reference,
    a base-bar price (`open`, `high`, `low`, `close`), or a numeric
    constant.
  - At least one operand SHALL be non-constant.
- `range {operand, min, max}` with inclusive bounds and `min <= max`.
  The operand SHALL be a feature reference, an episode reference or a
  base-bar price.
- `change {operand, lookback, op, value}` with `op` in `>`, `>=`, `<`,
  `<=`, a positive integer `lookback`, and a finite numeric `value`.
  The operand SHALL be a feature reference.
- `state {context_ref, in}`.
  - `context_ref` SHALL be declared in the spec's `contexts`.
  - `in` SHALL be a non-empty subset of `aligned`, `countertrend`,
    `neutral`, resolved per side by the existing HTF regime resolution.
- `temporal {mode, bars, of}` with `mode` in `held_for`, `within`, a
  positive integer `bars`, and `of` a non-temporal predicate.

A feature reference SHALL name:

- a `kind`;
- an optional `timeframe`, default `base`;
- an optional `source`;
- a `params` object.

Its validity, the `source` default and the valid `params` SHALL be
decided by the canonical feature-kind contract (see the requirement
"Feature operands resolve through the canonical feature-kind
contract"), not by the predicate layer.

An episode reference SHALL have the shape
`{"episode": {"ref", "entity", "index", "field"}}`:

- `ref` SHALL name an episode declared in `raw_spec.ema_stack_episode`;
- `entity` SHALL be omitted for an episode state field, and otherwise
  be one of `zone`, `false_break`, `up_leg`, `down_leg`, `wave`;
- `index` SHALL be given exactly when `entity` is given. It SHALL be
  `current` (0), `previous` (-1), a non-positive integer counted back
  from the latest touch, a positive integer naming the number in the
  episode, or `forming`. `forming` is allowed for `wave`, `up_leg` and
  `down_leg` only;
- `field` SHALL be a field defined for that entity.

The value SHALL be read from the episode projection of the evaluated
side. A missing value (no active episode, a censored episode, an entity
not reached yet, or an index out of range) SHALL be non-finite.

Any other class, operator or operand SHALL be rejected. In particular
the layer SHALL reject:

- negation;
- equality on numeric values;
- arithmetic expressions.

#### Scenario: Feature versus constant

- **WHEN** the predicate is `compare` of `adx` (`1h`, 14) `>=` 25
- **THEN** it SHALL be True exactly on base bars where the aligned 1h
  ADX(14) value is finite and at least 25.

#### Scenario: Feature versus feature

- **WHEN** the predicate is `compare` of `ema` (`1h`, 100) `>` `ema`
  (`1h`, 500)
- **THEN** it SHALL be True exactly on base bars where both aligned
  values are finite and the first is greater.

#### Scenario: Range

- **WHEN** the predicate is `range` over `rsi` (`5m`, 14) with `min` 40
  and `max` 65
- **THEN** it SHALL be True exactly where the value is finite and
  40 ≤ value ≤ 65.

#### Scenario: Context state

- **WHEN** the predicate is `state` with `context_ref` `htf_4h` and
  `in` [`aligned`]
- **THEN** for the long side it SHALL be True exactly where that
  context's state is `up`
- **AND** for the short side exactly where it is `down`.

#### Scenario: Unsupported operator is rejected

- **WHEN** a predicate uses `op` `==` or `!=`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Change with an unsupported shape is rejected

- **WHEN** a `change` predicate has a non-positive or non-integer `lookback`, a non-finite `value`, an operand that is not a
  feature reference, or an unknown field
- **THEN** static validation SHALL reject the spec.


### Requirement: Side semantics

A predicate SHALL evaluate identically for long and short unless it
declares an explicit `short` override. The override is allowed on
`compare`, `range` and `change` only, and replaces the listed fields
for the short side. On `change` the override MAY replace `op` and
`value` only; it SHALL NOT replace `operand` or `lookback`.

The layer SHALL NOT invert any predicate automatically for the short
side. A `side_relative` flag, or any equivalent automatic operand
swap, SHALL be rejected.

`state` SHALL remain side-relative, because `aligned`, `countertrend`
and `neutral` are the semantics of the existing HTF regime
resolution.

An episode reference SHALL be read from the episode of the evaluated
side, because an EMA stack episode exists per side. This SHALL NOT be
treated as automatic inversion. A `short` override SHALL NOT replace an
operand with an episode reference, and an override of an episode
predicate SHALL replace only `op`, `right` constants, `min` or `max` as
for any other predicate.

#### Scenario: Short override

- **WHEN** a predicate is `rsi < 70` with `short: {op: ">", right: 30}`
- **THEN** it SHALL evaluate `rsi < 70` for long and `rsi > 30` for
  short.

#### Scenario: Feature order differs by side via explicit override

- **WHEN** a predicate is `ema100 > ema500` with `short: {op: "<"}`
- **THEN** it SHALL evaluate `ema100 > ema500` for long and
  `ema100 < ema500` for short.

#### Scenario: Automatic inversion is rejected

- **WHEN** a predicate declares `side_relative: true`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Change override

- **WHEN** a `change` predicate is `rsi (5m, 14)` with `lookback` 6, `op` `>=`, `value` 5 and `short: {op: "<=", value: -5}`
- **THEN** it SHALL evaluate the rise of at least 5 for long and the fall of at least 5 for short
- **AND** a `short` override that names `operand` or `lookback` SHALL be rejected.

#### Scenario: Episode state field

- **WHEN** the predicate is `compare` of the episode reference
  `{ref: trend, field: touch_number}` `<` 3
- **THEN** it SHALL be True exactly on base bars where the evaluated
  side's episode is active, not censored, and its `touch_number` is
  less than 3.

#### Scenario: Relative entity versus relative entity

- **WHEN** the predicate is `compare` of `up_leg` index -1 field
  `range` `>` `up_leg` index -3 field `range`
- **THEN** on each bar it SHALL compare the previous up leg's range
  with that of the up leg three back from the latest touch
- **AND** it SHALL be False on bars where either does not exist.

#### Scenario: Malformed episode reference

- **WHEN** an episode reference names an undeclared `ref`, an unknown
  entity or field, gives `index` without `entity` or `entity` without
  `index`, or uses `forming` on `zone` or `false_break`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Episode reference in change is rejected

- **WHEN** the operand of a `change` predicate is an episode reference
- **THEN** static validation SHALL reject the spec.
