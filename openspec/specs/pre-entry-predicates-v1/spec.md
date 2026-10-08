# pre-entry-predicates-v1 Specification

## Purpose
An internal boolean layer turns canonical Strategy Engine features and
context into pre-entry conditions on the base timeline. The layer
computes no indicator and performs no alignment of its own.
## Requirements
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

### Requirement: Determinism

For identical market bars, plan columns, context bundle, predicate
parameters and side, a predicate SHALL return an identical boolean
series of the base frame's length.

#### Scenario: Repeated evaluation

- **WHEN** the same predicate is evaluated twice on identical inputs
- **THEN** both results SHALL be identical.

### Requirement: Feature operands resolve through the canonical feature-kind contract

The indicator layer SHALL expose one canonical feature-kind contract.
For each kind it SHALL provide:

- its schema;
- its default `source`;
- whether it is requestable as a standalone operand, which is false
  for kinds that require feature dependencies;
- its validator;
- its column label;
- the parameters that enter its identity.

The following SHALL derive their knowledge of kinds from this
contract, and SHALL NOT keep their own lists:

- `IndicatorRegistry` (`list_definitions`, `get_schema`,
  `validate_feature`);
- the feature planner's allowed kinds and label functions;
- `resolve_feature` identity parameters.

For every kind existing before this change, the following SHALL be
unchanged:

- schemas;
- validation errors;
- labels;
- node identities.

The predicate layer SHALL resolve feature operands only through this
contract. It SHALL NOT contain any of the following:

- indicator-kind names;
- per-kind source rules;
- per-kind parameter rules;
- a list of kinds.

#### Scenario: Unknown or non-requestable kind

- **WHEN** a feature operand names a kind the contract does not know,
  or one it marks as not requestable
- **THEN** the spec SHALL be rejected with the contract's error.

#### Scenario: Source and parameters decided by the kind contract

- **WHEN** a feature operand for `rsi` supplies `source: open`
- **THEN** the spec SHALL be rejected by the RSI kind contract's own
  validator
- **AND** the predicate layer SHALL contain no RSI-specific rule
  producing that rejection.

#### Scenario: Existing kinds unchanged by the contract

- **WHEN** a spec without `composite_setup` is planned and resolved
  after this change
- **THEN** its labels, `plan_hash` and feature identities SHALL equal
  those before this change.

### Requirement: Extension invariant for new feature kinds

When the indicator layer adds a new canonical feature kind, it SHALL
provide three things: its math in the canonical evaluator, a
feature-kind contract entry, and a warm-up policy.

Once it does, the kind SHALL be usable as a predicate operand, at any
supported timeframe and with the canonical completed-bar alignment,
without any of the following:

- a new setup component;
- a change to the predicate layer;
- a change to the `composite_setup` evaluator;
- a second indicator registry, math or alignment layer.

Every parameter of the new kind that changes its values SHALL be part
of its identity.

#### Scenario: Bollinger upper band as an operand

- **WHEN** the indicator layer adds a `bb_upper` kind with
  `{period, std}`, together with its math, contract entry and warm-up
  policy
- **THEN** `compare {left: {price: close}, op: ">", right: {feature:
  {kind: bb_upper, timeframe: 1h, params: {period: 20, std: 2}}}}` SHALL
  be a valid predicate
- **AND** `bb_upper` with `std` 2 and `std` 2.5 SHALL have different
  identities.

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

