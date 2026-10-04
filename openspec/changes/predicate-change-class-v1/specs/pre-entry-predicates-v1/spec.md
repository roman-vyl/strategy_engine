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

### Requirement: Non-finite values are not satisfied

On any bar where an operand of `compare`, `range` or `change` is
missing or non-finite, the predicate SHALL be False.

#### Scenario: Indicator warm-up

- **WHEN** an HTF ADX column has no completed value yet on a base bar
- **THEN** every predicate reading that column SHALL be False on that
  bar.

#### Scenario: Second point of a change is not available

- **WHEN** the operand of a `change` predicate is missing or non-finite at the second point, including the first
  `lookback` bars of the operand's timeframe in the frame
- **THEN** the predicate SHALL be False on that bar.

## ADDED Requirements

### Requirement: Change predicate

`change {operand, lookback, op, value}` SHALL be True on a base bar if and only if
`operand(j) − operand(j − lookback) <op> value`, where `j` is the last completed bar of the operand's own timeframe at that base
bar and `lookback` counts bars of that timeframe. For a base-timeframe operand the bars are base bars.

- Both points SHALL be values of the same series. The predicate SHALL NOT align a series of its own: for an operand on a
  higher timeframe it SHALL read the aligned column shifted by `lookback` times the ratio of that timeframe to the base
  timeframe.
- A higher-timeframe operand SHALL use its last completed bar, with no look-ahead, exactly as every other predicate does.
- `change` SHALL be a non-temporal predicate, and so MAY be the inner predicate of `temporal`.
- Evaluation cost SHALL be linear in the number of bars and SHALL NOT depend on `lookback`.

#### Scenario: Base-timeframe change

- **WHEN** a `change` predicate is `rsi` (`5m`, 14) with `lookback` 3, `op` `>=`, `value` 5 on a 5m base timeframe
- **THEN** it SHALL be True exactly on bars where the value is finite at the bar and three bars earlier and the difference is
  at least 5.

#### Scenario: Higher-timeframe change counts bars of that timeframe

- **WHEN** a `change` predicate is `rsi` (`1h`, 14) with `lookback` 2 on a 5m base timeframe
- **THEN** on a base bar it SHALL compare the last completed 1h value with the 1h value two completed 1h bars earlier
- **AND** the value SHALL stay constant across base bars of one 1h bar.

#### Scenario: Change under a temporal window

- **WHEN** `held_for 4` wraps a `change` predicate
- **THEN** it SHALL be True at bar i iff the change predicate is True on bars i−3 to i.
