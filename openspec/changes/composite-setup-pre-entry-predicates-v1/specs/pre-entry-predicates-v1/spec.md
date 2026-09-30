## Purpose

An internal boolean layer turns canonical Strategy Engine features and
context into pre-entry conditions on the base timeline. The layer
computes no indicator and performs no alignment of its own.

## ADDED Requirements

### Requirement: Predicate is an internal layer, not a strategy role

`PreEntryPredicate` SHALL be an internal evaluation contract. It SHALL
NOT be a strategy role or component:

- it SHALL NOT appear in any `*_SUPPORTED` allowlist;
- it SHALL NOT be accepted as a top-level item of `setups`,
  `components.blockers`, `direction`, `trigger`, exits, or managed
  phase rules.

In this change its only consumer SHALL be `composite_setup`.

#### Scenario: Predicate at top level is rejected

- **WHEN** a spec places a predicate object directly in `setups` or
  `components.blockers`
- **THEN** static validation SHALL reject the spec.

### Requirement: Canonical features and context only

A predicate SHALL obtain feature values only from columns of the
strategy's canonical `IndicatorPlan`, evaluated by
`RangeIndicatorEvaluator.evaluate_native`. It SHALL obtain base-bar
prices only from the frame's shared market arrays, and HTF regime only
from the `ContextBundle` built for the same evaluation.

A predicate SHALL NOT:

- compute an indicator;
- resample market data;
- align a higher-timeframe series;
- maintain its own indicator registry.

#### Scenario: Predicate reads the same series as an existing consumer

- **WHEN** a predicate references `rsi` on `5m` with period 14
- **AND** an existing exit or blocker already requests the same feature
- **THEN** both SHALL read the same plan column
- **AND** the feature SHALL be computed once for that evaluation.

#### Scenario: Higher-timeframe feature without lookahead

- **WHEN** a predicate references a feature on a timeframe that is an
  integral multiple of the base timeframe
- **THEN** on each base bar the predicate SHALL see the value of the
  last completed bar of that timeframe
- **AND** that value SHALL be exactly the one the existing completed-bar
  alignment produces.

### Requirement: Supported predicate classes

The layer SHALL support exactly the following classes:

- `compare {left, op, right}` with `op` in `>`, `>=`, `<`, `<=`.
  - Each operand SHALL be a feature reference, a base-bar price
    (`open`, `high`, `low`, `close`), or a numeric constant.
  - At least one operand SHALL be non-constant.
- `range {operand, min, max}` with inclusive bounds and `min <= max`.
  The operand SHALL be a feature reference or a base-bar price.
- `state {context_ref, in}`.
  - `context_ref` SHALL be declared in the spec's `contexts`.
  - `in` SHALL be a non-empty subset of `aligned`, `countertrend`,
    `neutral`, resolved per side by the existing HTF regime resolution.
- `temporal {mode, bars, of}` with `mode` in `held_for`, `within`, a
  positive integer `bars`, and `of` a non-temporal predicate.

A feature reference SHALL name:

- a `kind` among `ema`, `rsi`, `atr`, `adx`, `di_plus`, `di_minus`;
- an optional `timeframe`, default `base`;
- a positive integer `period`;
- for `ema` only, an optional `source`, default `close`.

Any other class, operator, operand or kind SHALL be rejected. In
particular the layer SHALL reject:

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

### Requirement: Temporal semantics

Temporal windows SHALL count base bars.

- `held_for N` SHALL be True at bar i if and only if the inner predicate
  is True on every bar from i−N+1 to i.
  - It SHALL be False while fewer than N bars exist.
- `within N` SHALL be True at bar i if and only if the inner predicate
  is True on at least one bar from max(0, i−N+1) to i.
- `bars` equal to 1 SHALL equal the inner predicate.
- Evaluation cost SHALL be linear in the number of bars and SHALL NOT
  depend on N.

#### Scenario: Held for N bars

- **WHEN** the inner predicate is True on bars 10..19 and False on bar 9
- **AND** the predicate is `held_for 5`
- **THEN** it SHALL be False on bars 10..13 and True on bars 14..19.

#### Scenario: Occurred within N bars

- **WHEN** the inner predicate is True only on bar 10
- **AND** the predicate is `within 5`
- **THEN** it SHALL be True on bars 10..14 and False on bar 15.

#### Scenario: Held for at the start of history

- **WHEN** the inner predicate is True on bars 0..2
- **AND** the predicate is `held_for 5`
- **THEN** it SHALL be False on bars 0..2.

### Requirement: Side semantics

A predicate SHALL evaluate identically for long and short unless it
declares otherwise:

- a `short` override on `compare` or `range` replaces the listed
  fields for the short side;
- `side_relative: true` on a `compare` whose operands are both
  non-constant swaps the operands for the short side.

`short` and `side_relative` SHALL NOT be combined. `state` SHALL be
side-relative by construction.

#### Scenario: Short override

- **WHEN** a predicate is `rsi < 70` with `short: {op: ">", right: 30}`
- **THEN** it SHALL evaluate `rsi < 70` for long and `rsi > 30` for
  short.

#### Scenario: Side-relative feature order

- **WHEN** a predicate is `ema100 > ema500` with `side_relative: true`
- **THEN** it SHALL evaluate `ema100 > ema500` for long and
  `ema500 > ema100` for short.

### Requirement: Non-finite values are not satisfied

On any bar where an operand of `compare` or `range` is missing or
non-finite, the predicate SHALL be False.

#### Scenario: Indicator warm-up

- **WHEN** an HTF ADX column has no completed value yet on a base bar
- **THEN** every predicate reading that column SHALL be False on that
  bar.

### Requirement: Determinism

For identical market bars, plan columns, context bundle, predicate
parameters and side, a predicate SHALL return an identical boolean
series of the base frame's length.

#### Scenario: Repeated evaluation

- **WHEN** the same predicate is evaluated twice on identical inputs
- **THEN** both results SHALL be identical.
