## MODIFIED Requirements

### Requirement: Supported predicate classes

The layer SHALL support exactly the following classes:

- `compare {left, op, right}` with `op` in `>`, `>=`, `<`, `<=`.
  - Each operand SHALL be a feature reference, a base-bar price
    (`open`, `high`, `low`, `close`), or a numeric constant.
  - At least one operand SHALL be non-constant.
- `range {operand, min, max}` with inclusive bounds and `min <= max`.
  The operand SHALL be a feature reference or a base-bar price.
- `change {operand, lookback, op, value}` with `op` in `>`, `>=`, `<`,
  `<=`, a positive integer `lookback`, and a finite numeric `value`.
  The operand SHALL be a feature reference.
- `state` in one of two forms:
  - context form `{context_ref, in}`:
    - `context_ref` SHALL be declared in the spec's `contexts`;
    - `in` SHALL be a non-empty subset of `aligned`, `countertrend`,
      `neutral`, resolved per side by the existing HTF regime
      resolution.
  - structure form `{structure_ref, field, op, value}` or
    `{structure_ref, field, in}`:
    - `structure_ref` SHALL be declared in the spec's
      `market_structure`;
    - `field` SHALL be a state field of that structure;
    - `op` SHALL be one of `<`, `<=`, `>`, `>=` with a finite numeric
      `value`, allowed on numeric fields;
    - `in` SHALL be a non-empty set of integers for an integer field,
      or of enumerated values for an enumerated field (`phase`);
    - exactly one of `op`/`value` or `in` SHALL be given.
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


#### Scenario: Structure state

- **WHEN** the predicate is `state` with `structure_ref` `trend`,
  `field` `touch_number`, `op` `<` and `value` 3
- **THEN** it SHALL be True exactly on base bars where the evaluated
  side's episode is active, not censored, and its `touch_number` is
  less than 3.

#### Scenario: Malformed structure state

- **WHEN** a structure-form `state` names an undeclared
  `structure_ref`, an unknown field, both `op` and `in`, or `in` on a
  non-integer numeric field
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

`state` SHALL remain side-relative. In the context form, `aligned`,
`countertrend` and `neutral` are the semantics of the existing HTF
regime resolution. In the structure form, the value SHALL be read from
the projection of the evaluated side, because a trend episode exists
per side. A structure-form `state` SHALL NOT take a `short` override.

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

#### Scenario: Structure state per side

- **WHEN** a structure-form `state` on `touch_number` is evaluated for
  long and for short
- **THEN** the long result SHALL read the long episode and the short
  result the short episode.
