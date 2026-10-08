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
  - `context_ref` SHALL be declared in the spec's `contexts` as an
    `htf_context`.
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

#### Scenario: Episode field versus constant

- **WHEN** the predicate is `range` over the episode field
  `touch_number` of context `episode` with `min` 1 and `max` 2
- **THEN** it SHALL be True exactly on base bars where the side's
  episode is active, not censored, and its `touch_number` is 1 or 2.

## ADDED Requirements

### Requirement: Episode operands

An episode reference SHALL have the shape
`{"episode": {"context_ref", "field", "wave"}}`:

- `context_ref` SHALL name a declared `ema_stack_episode` context;
- `field` SHALL be an episode field or a wave field of that provider;
- `wave` SHALL be required for a wave field and rejected for an
  episode field. Its value SHALL be `current`, `previous`, `forming`
  or an integer `k >= 1`.

The value on a bar SHALL be the provider's field for the side being
evaluated. This is the definition of the episode, which exists per
side; it is not an automatic inversion of the predicate.

An episode reference SHALL be rejected:

- as the operand of `change`;
- inside a `short` override, which still replaces only operators and
  bounds.

A NaN episode value SHALL make the predicate False on that bar, as for
any non-finite operand.

#### Scenario: Wave selector

- **WHEN** a predicate is `compare` of the episode field `retracement`
  with `wave` `previous` `<=` 0.5
- **THEN** on each bar it SHALL read the retracement of wave
  `touch_number − 1` of the evaluated side
- **AND** it SHALL be False on bars where that wave does not exist.

#### Scenario: Same predicate, both sides

- **WHEN** a predicate `range(touch_number, 1, 1)` is evaluated for long
  and for short
- **THEN** the long result SHALL read the long episode and the short
  result the short episode.

#### Scenario: Malformed episode reference

- **WHEN** an episode reference names an unknown field, omits `wave`
  for a wave field, sets `wave` for an episode field, or names a
  context that is not an `ema_stack_episode`
- **THEN** static validation SHALL reject the spec.
