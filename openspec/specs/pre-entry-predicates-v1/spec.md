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
    a segment reference, a ratio, a base-bar price (`open`, `high`,
    `low`, `close`), or a numeric constant.
  - At least one operand SHALL be non-constant.
- `range {operand, min, max, bounds?, empty?}` as defined in the
  requirements "Range bounds" and "Range empty policy". The operand SHALL be a
  feature reference, an episode reference, a segment reference, a
  ratio or a base-bar price.
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

A segment reference and a ratio SHALL be defined by the requirements
"Segment source fields", "Segment aggregation fields", "Segment points", "Segment window", "Segment value" and "Ratio operand".

Any other class, operator or operand SHALL be rejected. In particular
the layer SHALL reject:

- negation;
- equality on numeric values;
- arithmetic expressions other than the single `ratio` operand.

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

#### Scenario: Range with a no-control side

- **WHEN** the predicate is `range` over a ratio with `min` 0.32, `max`
  null, `bounds` exclusive and `empty` pass
- **THEN** it SHALL be False exactly where the ratio is finite and at
  most 0.32, and True everywhere else.

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
for the short side. On `range` the override MAY replace `min`, `max`,
`bounds` and `empty`; it SHALL NOT replace `operand`. On `change` the override MAY replace `op` and
`value` only; it SHALL NOT replace `operand` or `lookback`.

The layer SHALL NOT invert any predicate automatically for the short
side. A `side_relative` flag, or any equivalent automatic operand
swap, SHALL be rejected.

`state` SHALL remain side-relative, because `aligned`, `countertrend`
and `neutral` are the semantics of the existing HTF regime
resolution.

An episode reference SHALL be read from the episode of the evaluated
side, because an EMA stack episode exists per side. A segment reference
SHALL read the points of the evaluated side's episode and SHALL negate
its series on the short side, so that "with the trade" and "against the
trade" keep their meaning; a ratio inherits the side behaviour of its
operands. This SHALL NOT be treated as automatic inversion: no operand
is swapped and no operator is changed. A `short` override SHALL NOT replace an
operand with an episode reference, a segment reference or a ratio, and
an override of a predicate with such an operand SHALL replace only `op`, `right` constants, `min` or `max` as
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

#### Scenario: Segment on the short side

- **WHEN** a segment over the series `x` with `value` level and `aggregate` sum is evaluated for the short side
- **THEN** it SHALL aggregate `−x` over the segment of the short side's episode.

### Requirement: Non-finite values are not satisfied

On any bar where an operand of `compare`, `range` or `change` is
missing or non-finite, the predicate SHALL be False. The only exception
is a `range` that declares `empty: pass`, which SHALL be True on such a
bar. There is no negation, so no other predicate can become True on a
missing operand.

#### Scenario: Indicator warm-up

- **WHEN** an HTF ADX column has no completed value yet on a base bar
- **THEN** every predicate reading that column SHALL be False on that
  bar.

#### Scenario: Second point of a change is not available

- **WHEN** the operand of a `change` predicate is missing or non-finite at the second point, including the first
  `lookback` bars of the operand's timeframe in the frame
- **THEN** the predicate SHALL be False on that bar.

#### Scenario: Empty pass

- **WHEN** a `range` with `empty: pass` reads a segment that is missing
  on a bar because the episode has no current touch
- **THEN** the predicate SHALL be True on that bar
- **AND** the same range with the default `empty` SHALL be False.

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

### Requirement: Segment operand shape

A segment reference SHALL be `{"segment": {"episode", "of", "from", "to", "aggregate", "value"?, "span"?, "top"?, "window"?, "negate"?, "eligibility"?}}`;
`episode`, `of`, `from`, `to` and `aggregate` are required and no other field is allowed. Their values are defined by the
requirements "Segment source fields", "Segment aggregation fields", "Segment k-bar change", "Segment absolute-change aggregates" and "Segment eligibility".

#### Scenario: Malformed segment

- **WHEN** a segment names an undeclared episode, an unknown kind, a pair such as `current → peak`, an unknown `aggregate`,
  `value` or `window`, a non-positive `last_n`, a missing required field, or an unknown field such as `select`
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment source fields

`episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`. `of` SHALL be a feature reference resolved by the
canonical feature-kind contract, or `{"difference": {"left", "right"}}` of two such references (the series `left − right`),
every feature on the base timeframe. `from` → `to` SHALL be `origin → peak`, `peak → current` or `origin → current`.

#### Scenario: Higher-timeframe series

- **WHEN** a feature of `of` is on a timeframe other than the base timeframe
- **THEN** evaluation SHALL fail closed.

#### Scenario: Difference of two EMAs

- **WHEN** `of` is the difference of `ema` (period 5) and `ema` (period 500)
- **THEN** the series SHALL equal EMA5 − EMA500 on every bar where both are finite, and be non-finite elsewhere.

### Requirement: Segment aggregation fields

`aggregate` SHALL be `sum`, `mean_per_bar`, `max`, `min`, `abs_sum`, `top_abs_sum` or `top_abs_share`. `value` SHALL be `level` (default),
`change` or `change_over`. `window` SHALL be `null` (default, the whole leg) or `{"last_n": N}` with `N` a positive integer.
`negate` SHALL be a boolean, default `false`. `max`, `min`, `abs_sum`, `top_abs_sum` and `top_abs_share` SHALL be allowed only with `value`
`change` or `change_over`, and `sum` and `mean_per_bar` SHALL be rejected with `change_over`. `top_abs_sum` and `top_abs_share` SHALL require `top` (a positive integer) and a non-null `window`; `top`
SHALL be rejected with any other aggregate.

#### Scenario: Invalid aggregation field

- **WHEN** `aggregate`, `value` or `window` has another value, `last_n` is not a positive integer, `max` is used with `level`,
  `sum` is used with `change_over`,
  `top_abs_sum` or `top_abs_share` has no `top` or a null `window`, or `top` is given with another aggregate
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment points

On base bar `t`, for the evaluated side, the points SHALL come from the current touch `m = touch_number[t]` of the episode:
`origin` is the origin bar `S*` of wave `m`, `peak` its peak bar `P`, `current` is `t`. The leg SHALL be the bars `a..e`
of the chosen pair, both ends inclusive. Only bars `≤ t` SHALL be read and the operand SHALL have no lookback window other
than its declared `window`.

#### Scenario: Peak bar belongs to both legs

- **WHEN** one segment is `origin → peak` and another `peak → current` on the same bar
- **THEN** bar `P` SHALL be counted in both.

#### Scenario: Before the first touch

- **WHEN** the episode is active and `touch_number` is 0, or the episode is inactive or censored
- **THEN** the segment SHALL be missing.

### Requirement: Segment window

With `x` the series of `of`, negated on the short side before everything else, the window SHALL be the bars `s..e` of the
leg, with `s = a` for `window = null` and `s = max(a, e − N + 1)` for `{"last_n": N}`, so a leg shorter than `N` is used
whole; `bars = e − s + 1`.

#### Scenario: Window longer than the leg

- **WHEN** `last_n` is larger than the number of bars of the leg
- **THEN** the whole leg SHALL be used
- **AND** the result SHALL equal the one with `window` null.

### Requirement: Segment value

With `x` and the window `s..e` as above, `value = level` SHALL aggregate `x[u]`, `value = change` SHALL aggregate
`Δ[u] = x[u] − x[u−1]` (reading `x[s−1]`) and `value = change_over` SHALL aggregate the `span`-bar changes defined by the requirement "Segment k-bar change", for `u = s..e` (`level`, `change`). `sum` SHALL be the sum and `mean_per_bar` the sum divided by
`bars`; `max`, `min`, `abs_sum`, `top_abs_sum` and `top_abs_share` SHALL be defined by the requirements "Segment extremum aggregates" and "Segment absolute-change aggregates". `negate = true` SHALL multiply the result by −1. Every bar SHALL count with its sign. The value SHALL be missing
when any `x` it reads is non-finite, and its cost SHALL NOT depend on leg lengths.

#### Scenario: Pullback speed toward the anchor

- **WHEN** a segment is the difference EMA5 − EMA500, `peak → current`, `change`, `last_n` 75, `mean_per_bar`, `negate`, long
  side, bar `t`, current touch `m ≥ 1`
- **THEN** its value SHALL be `−(x[t] − x[s−1]) / bars` with `s = max(P_m, t − 74)` and `bars = t − s + 1`.

#### Scenario: Non-finite value inside the window

- **WHEN** a value the window reads is non-finite
- **THEN** the segment SHALL be missing on that bar.

### Requirement: Ratio operand

A ratio SHALL have the shape `{"ratio": {"left", "right"}}`, each side an operand of the layer other than a ratio, and not
both constants. Its value SHALL be `left / right`, and SHALL be missing when either side is missing or non-finite or when
`right ≤ 0`.

#### Scenario: Zero denominator

- **WHEN** the right side is 0 on a bar
- **THEN** the ratio SHALL be missing on that bar.

#### Scenario: Nested ratio is rejected

- **WHEN** a side of a ratio is itself a ratio
- **THEN** static validation SHALL reject the spec.

### Requirement: Range bounds

In `range {operand, min, max, bounds?, empty?}`, `min` and `max` SHALL be present and each SHALL be a finite number or
`null`, where `null` means no control on that side. `bounds` SHALL be `inclusive` (default: `min ≤ value ≤ max`) or
`exclusive` (`min < value < max`); a `null` side imposes nothing. With both set, `min ≤ max` (`inclusive`) or `min < max`
(`exclusive`) SHALL hold.

#### Scenario: Band with two sliders

- **WHEN** a range has `min` 0.44, `max` 3.5, `bounds` exclusive, `empty` pass
- **THEN** it SHALL be False exactly where the operand is finite and `≤ 0.44` or `≥ 3.5`.

#### Scenario: Invalid band

- **WHEN** a range has `bounds` exclusive and `min` equal to `max`, an unknown `bounds` value, or a non-finite bound
- **THEN** static validation SHALL reject the spec.

#### Scenario: Existing range unchanged

- **WHEN** a spec contains `range` over `rsi` with `min` 40 and `max` 65 and nothing else
- **THEN** its mask and its node identity SHALL equal those before this change.

### Requirement: Range empty policy

`empty` SHALL be `block` (default) or `pass`: the result of a `range` on a bar where its operand is missing or non-finite.
A range with both bounds `null` SHALL be True on every bar with a finite operand and follow `empty` elsewhere.

#### Scenario: Both sliders on no control

- **WHEN** a range has `min` null, `max` null and `empty` pass
- **THEN** it SHALL be True on every bar.

#### Scenario: Unknown empty policy

- **WHEN** `empty` is neither `block` nor `pass`
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment k-bar change

`value: change_over` SHALL require `span`, a positive integer, and `span` SHALL be rejected with any other `value`. With `x`
the series of `of` (negated on the short side first), the values over the window `s..e` SHALL be
`D[u] = x[u] − x[u−span]` for `u = s+span−1..e`. The earliest value reads `x[s−1]`, and no earlier bar. The result SHALL be
missing when the window has fewer than `span` bars or any `x` read is non-finite.

#### Scenario: Three-bar change on the pullback

- **WHEN** a segment is `peak → current`, `change_over` with `span` 3, `last_n` 75, `min`, `negate`, long side
- **THEN** its value SHALL be `−min` over `u = s+2..t` of `x[u] − x[u−3]` with `s = max(P, t − 74)`.

#### Scenario: Window shorter than the span

- **WHEN** the window has fewer than `span` bars
- **THEN** the segment SHALL be missing.

### Requirement: Segment extremum aggregates

`max` and `min` SHALL return the largest and the smallest value of the series chosen by `value` over the window `s..e`. They
SHALL be missing exactly when the series is missing on the window.

#### Scenario: Strongest move away from the anchor

- **WHEN** a segment is `origin → peak`, `change_over` with `span` 3, `last_n` 75, `max`
- **THEN** its value SHALL be the largest `x[u] − x[u−3]` over the last 75 bars of the impulse.

### Requirement: Segment absolute-change aggregates

`abs_sum` SHALL return the sum of `|v[u]|` and `top_abs_sum` the sum of the `top` largest `|v[u]|` over the window `s..e`,
with `v` the series chosen by `value` (`change` or `change_over`). Every bar of the window SHALL count, whether it moves
toward or away from the anchor. With fewer than `top` values in the window `top_abs_sum` SHALL be the sum of all of them.
Ties SHALL NOT change the sum.

#### Scenario: Five largest changes

- **WHEN** a segment is `peak → current`, `change`, `last_n` 75, `top_abs_sum` with `top` 5
- **THEN** its value SHALL be the sum of the five largest `|x[u] − x[u−1]|` over the last 75 bars of the pullback.

#### Scenario: Window shorter than top

- **WHEN** the window has 3 bars and `top` is 5
- **THEN** `top_abs_sum` SHALL equal `abs_sum`
- **AND** `top_abs_share` SHALL be missing (a window of `top` bars or fewer has no normalized share).

#### Scenario: Normalized share

- **WHEN** a segment is `peak → current`, `change`, `last_n` 75, `top_abs_share` with `top` 5 and the window has `N` > 5 bars
- **THEN** its value SHALL be `(S ÷ A − 5/N) ÷ (1 − 5/N)` with `S` the sum of the five largest `|x[u] − x[u−1]|` and `A` their sum over all `N` bars
- **AND** it SHALL be 0 when all `N` changes have equal magnitude and 1 when only five are non-zero
- **AND** it SHALL be missing when `A` is 0.

### Requirement: Segment eligibility shape

A segment MAY carry `eligibility: {"legs_min_bars", "window", "impulse_positive", "pullback_min_bars"}`. All keys SHALL be optional;
`legs_min_bars`, `window` and `pullback_min_bars` SHALL be positive integers and `impulse_positive` a boolean; `impulse_positive` SHALL require
`window`; unknown keys SHALL be rejected. The `window` of the eligibility SHALL be independent of the segment's own `window`.

#### Scenario: Malformed eligibility

- **WHEN** `eligibility` has an unknown key, a non-positive `legs_min_bars`, `window` or `pullback_min_bars`, a non-boolean `impulse_positive`, or
  `impulse_positive` without `window`
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment eligibility leg length

With `legs_min_bars`, a segment SHALL be missing on bar `t` unless both `origin → peak` and `peak → current` of the current
touch have at least that many bars (inclusive ends), counted on the whole legs before any window. The condition SHALL be
evaluated on the legs of the segment's episode whatever leg the segment itself reads.

#### Scenario: Short leg

- **WHEN** the pullback has 2 bars and `legs_min_bars` is 3
- **THEN** the segment SHALL be missing
- **AND** a range over a ratio of such segments with `empty: pass` SHALL not block the bar.

### Requirement: Segment eligibility pullback length

With `pullback_min_bars` M, a segment SHALL be missing on bar `t` unless `peak → current` of the current touch has at least M
bars (inclusive ends), counted on the whole leg, whatever leg the segment itself reads.

#### Scenario: Boundary

- **WHEN** `pullback_min_bars` is 24 and the pullback has 23 bars, then 24 bars
- **THEN** the segment SHALL be missing on the first and have its value on the second.

### Requirement: Segment eligibility window

With `window` W, a segment SHALL be missing on bar `t` unless every one-bar change of the last W bars of `origin → peak` and
of the last W bars of `peak → current` is finite (each change reads the bar before it). The same two windows SHALL be used
whatever the segment's own `window`, so branches that differ in their own window share one eligibility.

#### Scenario: Non-finite change in the impulse

- **WHEN** one one-bar change in the last W bars of the impulse is non-finite
- **THEN** every segment with that eligibility SHALL be missing on that bar, including one that reads only the pullback.

### Requirement: Segment eligibility impulse direction

With `impulse_positive` true, a segment SHALL be missing on bar `t` unless the sum of the one-bar changes of `x` over the
last `window` bars of `origin → peak` is strictly greater than 0 (the impulse moved away from the anchor). The condition
SHALL be the same for every segment carrying the same eligibility.

#### Scenario: Impulse did not move away

- **WHEN** the impulse sum of changes in its window is 0 or negative
- **THEN** every segment with `impulse_positive` SHALL be missing on that bar.

### Requirement: Candle operand shape

A candle reference SHALL be `{"candle": {"episode", "leg", "timeframe", "direction", "atr"?}}`. `episode`, `leg`, `timeframe` and
`direction` are required and no other field is allowed. `episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`.
`leg` SHALL be `impulse` or `pullback`, `direction` SHALL be `with` or `against`, and `timeframe` SHALL be a timeframe that is a
multiple of the base timeframe.

#### Scenario: Malformed candle

- **WHEN** a candle names an undeclared episode, an unknown `leg` or `direction`, a timeframe that is not a multiple of the base
  timeframe, a missing required field or an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Candle operand use

A candle reference SHALL be accepted wherever a segment reference is accepted: as a side of a `ratio`, as the operand of a `range`
and as an operand of a `compare`. It SHALL NOT be accepted as the operand of a `change`. A short override SHALL NOT replace it.

#### Scenario: Candle as change operand

- **WHEN** a `change` predicate has a candle reference as its operand
- **THEN** static validation SHALL reject the spec.

### Requirement: Candle ATR normalisation

When `atr` (feature kind `atr_wilder`, same timeframe as the candle) is present, each candle body SHALL be divided by that
candle's ATR before the maximum is taken; a candle without a positive ATR SHALL be skipped. Without `atr`, bodies are in price units.

#### Scenario: Forming candle

- **WHEN** the last candle of the pullback is still forming on the evaluated bar
- **THEN** its body SHALL be divided by the ATR of the candle before it.

#### Scenario: Closed candle

- **WHEN** a candle of the impulse ends inside the impulse
- **THEN** its body SHALL be divided by its own ATR.

#### Scenario: Different ATR timeframe

- **WHEN** `atr` has a timeframe other than the candle's `timeframe` or a kind other than `atr_wilder`
- **THEN** static validation SHALL reject the spec.

### Requirement: Candle legs

For the evaluated side's episode and the current touch of bar `t`, the `impulse` leg SHALL be the bars from the origin bar `S*`
to the peak bar `P` inclusive, and the `pullback` leg SHALL be the bars from `P+1` to `t` inclusive. Only bars up to `t` SHALL be
read. When the touch has no pullback bars (`t = P`), no active episode, or a censored episode, the value SHALL be missing.

#### Scenario: Peak bar

- **WHEN** the pullback leg is evaluated on the peak bar itself
- **THEN** the candle value SHALL be missing
- **AND** the peak bar SHALL be counted in the impulse only.

### Requirement: Candles assembled from base bars

The candles of a leg SHALL be assembled from the base bars of that leg only. Base bars SHALL be grouped by bucket on the
`timeframe` grid, aligned to the epoch with the bucket start included and the bucket end excluded. The open of a candle SHALL be
the open of its first leg bar in the bucket and the close the close of its last leg bar in the bucket that is not after `t`.
A candle SHALL therefore be clipped at the start of the leg and, for the impulse, at `P`.

#### Scenario: Edge candle

- **WHEN** a 1h bucket starts before the pullback and the pullback starts inside it
- **THEN** the candle of that bucket in the pullback SHALL open at the first pullback bar.

#### Scenario: Forming candle

- **WHEN** the bar `t` lies inside a bucket that has not ended
- **THEN** the candle of that bucket SHALL close at the close of bar `t`
- **AND** the value on the next bar SHALL take the new close without waiting for the bucket to end.

### Requirement: Candle body and direction

A candle's body with the trade SHALL be `close − open` when positive on the long side and `open − close` when positive on the
short side; its body against the trade SHALL be the opposite one. The value of the candle operand SHALL be the largest (normalised, when `atr` is set) body of the
requested direction over the candles of the leg, and 0 when no candle has a positive body in that direction. The value SHALL be
missing when an open or close that enters is not finite.

#### Scenario: Pullback without a counter candle

- **WHEN** no candle of the pullback closes against the trade
- **THEN** the value SHALL be 0, a valid value.

#### Scenario: Impulse without a with-trade candle

- **WHEN** a ratio has the impulse with-trade value as its right side and that value is 0
- **THEN** the ratio SHALL be missing on that bar
- **AND** a `range` with `empty: pass` SHALL not block the bar.

#### Scenario: Short side mirror

- **WHEN** the evaluated side is short and a candle closes above its open in the pullback
- **THEN** that candle SHALL count as against the trade.

### Requirement: Candle operand per touch

The impulse value SHALL be the same on every bar of one touch. The pullback value on bar `t` SHALL depend only on bars up to
`t`: changing any later bar SHALL NOT change it. A candle assembled from bars with gaps in the base series SHALL use only the
bars that exist.

#### Scenario: No lookahead

- **WHEN** the bars after `t` are replaced
- **THEN** the candle values on bars up to `t` SHALL be unchanged.

### Requirement: Wilder ATR feature

A feature kind `atr_wilder` SHALL exist with the single parameter `period`, source close and any timeframe. Its first true range
SHALL be `high − low`, its first value SHALL be the mean of the first `period` true ranges, and each next value SHALL be
`(previous · (period − 1) + true range) / period`; values before the first SHALL be missing. The `atr` feature SHALL be
unchanged.

#### Scenario: Seed

- **WHEN** a series has 20 candles and `period` is 14
- **THEN** the first 13 values SHALL be missing and the 14th SHALL be the mean of the first 14 true ranges.

### Requirement: Segment touch selection

A segment MAY carry `touch`, `current` (default) or `previous`. With `previous` the points of the segment SHALL be read from the
touch row before the current touch row of the same episode. With `previous` the segment SHALL be `origin → peak`, other pairs
SHALL be rejected, and it SHALL be missing on a bar whose current touch is the first of its episode. A touch of an earlier
episode SHALL NOT be read.

#### Scenario: First touch

- **WHEN** a `previous` segment is evaluated on a bar of the first touch of an episode
- **THEN** its value SHALL be missing
- **AND** a `range` over a ratio of it with `empty: pass` SHALL not block the bar.

#### Scenario: Previous pair rejected

- **WHEN** a `previous` segment is `peak → current` or `origin → current`
- **THEN** static validation SHALL reject the spec.

### Requirement: Previous touch points

For a bar `t` with current touch row `r` and `touch_number ≥ 2` in the episode, a `previous` segment SHALL use the origin bar
and the peak bar of row `r − 1`, both ends inclusive. Only bars up to the peak SHALL be read, so no bar after `t` is read.

#### Scenario: Second touch

- **WHEN** the current touch is the second of its episode
- **THEN** a `previous` segment SHALL span the origin and peak of the first touch.

### Requirement: Segment series by side

The `of` field of a segment MAY be `{"by_side": {"long", "short"}}` with exactly those two feature references, both on the base
timeframe. The evaluated side SHALL read its own feature. A `by_side` series SHALL NOT be negated on the short side; a single
feature or a difference SHALL be negated as before. `negate` SHALL keep its meaning.

#### Scenario: Directional index by side

- **WHEN** `of` is `by_side` with `di_plus` for long and `di_minus` for short and the evaluated side is short
- **THEN** the series SHALL be the `di_minus` values, not negated.

#### Scenario: Malformed by_side

- **WHEN** `by_side` lacks `long` or `short`, has another key, or a feature is not on the base timeframe
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment value from start

`value: from_start` SHALL read `x[u] − x[s]` for `u = s … e`, `s` being the first bar of the window. It SHALL be allowed with
`sum`, `mean_per_bar`, `max` and `min`, and SHALL be rejected with `abs_sum`, `top_abs_sum` and `top_abs_share`. The value
SHALL be missing when any `x[s … e]` is not finite.

#### Scenario: Rise to the peak

- **WHEN** a segment is `origin → peak`, `from_start`, `max` over a series `D`
- **THEN** its value SHALL be `max(D[S* … P]) − D[S*]`.

#### Scenario: Average area

- **WHEN** a segment is `origin → peak`, `from_start`, `mean_per_bar` over a series `D`
- **THEN** its value SHALL be `mean(D[S* … P]) − D[S*]`.

#### Scenario: One-bar window

- **WHEN** the window has one bar
- **THEN** every `from_start` aggregate SHALL be 0 (`sum`, `mean_per_bar`, `max`, `min`).

### Requirement: Ratio denominator floor

A ratio MAY carry `right_floor`, a finite number, default 0. The ratio SHALL be missing when the right side is not greater than
`right_floor`. A non-finite or non-numeric `right_floor` SHALL be rejected.

#### Scenario: Tiny positive denominator

- **WHEN** `right_floor` is 1e-6 and the right side is 1e-7
- **THEN** the ratio SHALL be missing.

### Requirement: Directional index wave ratio

A ratio of a `from_start` segment of `touch` `current` over one of `touch` `previous`, both `origin → peak` over the same series,
with `right_floor` 1e-6, SHALL be missing when the previous wave's value is not greater than 1e-6 or when either side is missing.
A current wave value not greater than 0 SHALL stay a value.

#### Scenario: Previous wave without a rise

- **WHEN** the previous wave's value is 0, negative or at most 1e-6
- **THEN** the ratio SHALL be missing and the entry SHALL not be blocked.

#### Scenario: Weak new wave

- **WHEN** the current wave's rise is 0.5 and the previous wave's rise is 1
- **THEN** the ratio SHALL be 0.5 and a `range` with `min` 0.7 and `bounds exclusive` SHALL block the bar.

### Requirement: Segment end at the touch bar

A segment MAY end at `touch`, the touch bar of the CURRENT touch row. `to: touch` SHALL be allowed only with `touch: current` and
`from: peak`; any other combination SHALL be rejected. The segment SHALL span the peak bar and the touch bar of the current touch,
both ends inclusive, and SHALL NOT change on the bars after the touch bar. The touch bar of the current touch is never after the
evaluated bar, so no bar after the evaluated bar is read.

#### Scenario: Current pullback

- **WHEN** the current touch has its touch bar at bar 30 and the evaluated bar is 32
- **THEN** a `peak → touch` segment SHALL span the peak bar and bar 30 on both bars 30 and 32.

### Requirement: Segment end at the next origin

A segment MAY end at `next_origin`, the origin bar of the CURRENT touch row. `to: next_origin` SHALL be allowed only with
`touch: previous` and `from: peak`; any other combination SHALL be rejected. The segment SHALL span the peak bar of the touch row
before the current one in the same episode and the origin bar of the current touch row, both ends inclusive, and SHALL be missing
on the first touch of an episode and when the origin bar is not after that peak bar.

#### Scenario: Previous pullback

- **WHEN** the current touch is the second of its episode and a segment is `peak → next_origin`, `touch: previous`
- **THEN** it SHALL span the peak bar of the first touch and the origin bar of the second touch.

#### Scenario: Next origin end rejected

- **WHEN** `to: next_origin` is used with `touch: current` or with `from: origin`
- **THEN** static validation SHALL reject the spec.

### Requirement: Counter-trade directional index wave ratio

A ratio of a `from_start` segment `peak → touch` of `touch` `current` over a `from_start` segment `peak → next_origin` of `touch`
`previous`, both over a `by_side` series with `long = di_minus` and `short = di_plus`, and `right_floor` 1e-6, SHALL be missing
when the previous pullback's value is not greater than 1e-6 or when either side is missing. A current value not greater than 0
SHALL stay a value.

#### Scenario: Violent pullback

- **WHEN** the current pullback's counter-DI rise is 2 and the previous pullback's rise is 1
- **THEN** the ratio SHALL be 2 and a `range` with `max` 1.5 and `bounds exclusive` SHALL block the bar.

#### Scenario: Previous pullback without a rise

- **WHEN** the previous pullback's value is 0, negative or at most 1e-6
- **THEN** the ratio SHALL be missing and the entry SHALL not be blocked.

#### Scenario: Short side

- **WHEN** the evaluated side is short
- **THEN** the series SHALL be `di_plus`, not negated.

### Requirement: Leg mean operand shape

A leg mean reference SHALL be `{"leg_mean": {"episode", "leg", "field"}}`; all three are required and no other field is allowed.
`episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`, `leg` SHALL be `impulse` or `pullback` and `field` SHALL be
`volume`, `open_interest`, `force_with` or `force_against`. It SHALL be accepted as a side of a `ratio`, as the operand of a `range` and of a
`compare`, and rejected as the operand of a `change`.

#### Scenario: Malformed leg mean

- **WHEN** a leg mean names an undeclared episode, an unknown `leg` or `field`, lacks a required field or has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg mean value

On each bar `t` the impulse leg SHALL be the base bars from `origin_bar` to `peak_bar` of the current touch and the pullback leg the
base bars from `peak_bar + 1` to `t`, both ends inclusive. The value SHALL be the arithmetic mean of the field over the leg's bars
and SHALL be missing when the current touch has no valid wave, when the leg is empty or when any bar of the leg has a non-finite
field. Bars after `t` SHALL NOT be read.

#### Scenario: Pullback starts after the peak

- **WHEN** `t` is the peak bar
- **THEN** the pullback mean SHALL be missing.

#### Scenario: Legs

- **WHEN** a wave has origin 10, peak 14 and `t` = 20
- **THEN** the impulse mean SHALL average bars 10 to 14 and the pullback mean bars 15 to 20.

#### Scenario: Bar without open interest

- **WHEN** the field is `open_interest` and a bar of the leg has no open interest
- **THEN** the leg mean, leg sum and leg top mean of that leg SHALL be missing.

### Requirement: Volume ratio filter

`range(ratio(leg_mean(pullback, volume), leg_mean(impulse, volume)))` with `bounds` `exclusive` and `empty: pass` SHALL block an
entry when the ratio is not greater than `min` or not less than `max` (both inclusive), each bound optional. A zero or missing impulse mean SHALL make
the ratio missing, and a missing ratio SHALL pass.

#### Scenario: Zero impulse volume

- **WHEN** the impulse leg has mean volume 0
- **THEN** the entry SHALL pass.

#### Scenario: Threshold

- **WHEN** the ratio equals `min` or equals `max`
- **THEN** the entry SHALL be blocked.

### Requirement: Candle force series

For the field `force_with` or `force_against` the series averaged by a leg mean SHALL be the candle force on the base bars,
`F[u] = (close[u] − close[u−1]) × volume[u]`, multiplied by `+1` for `force_with` on the long side and `force_against` on the short side
and by `−1` for `force_against` on the long side and `force_with` on the short side. The series SHALL be 0 on bar 0, the first bar of the data window, and missing on any other bar where
`close[u]`, `close[u−1]` or `volume[u]` is not finite. The leg mean of it SHALL be the arithmetic mean over all bars of the leg, with the legs
and the missing rules of the leg mean operand. The impulse leg `[S*, P]` SHALL read `close[S*−1]` for its first bar.

#### Scenario: Long side

- **WHEN** the side is long and a pullback bar closes 2 below the previous close on volume 10
- **THEN** its `force_against` SHALL be 20 and its `force_with` SHALL be −20.

#### Scenario: Short side mirror

- **WHEN** the side is short and a bar closes 2 above the previous close on volume 10
- **THEN** its `force_against` SHALL be 20.

#### Scenario: First bar of the series

- **WHEN** the impulse leg starts at bar 0
- **THEN** the force of bar 0 SHALL be 0 and the mean SHALL average it like any other bar.

### Requirement: Force ratio filter

`range(ratio(leg_mean(pullback, force_against), leg_mean(impulse, force_with)))` with `bounds` `exclusive` and `empty: pass` SHALL
block an entry when the ratio is not greater than `min` or not less than `max` (both inclusive), each bound optional. A missing ratio SHALL
pass. The ratio SHALL be missing when the impulse mean is not greater than 0 or either mean is missing. A negative pullback mean SHALL
stay a value. Bars after the evaluated bar SHALL NOT be read.

#### Scenario: Impulse without force

- **WHEN** the impulse mean force with the trade is 0 or negative
- **THEN** the ratio SHALL be missing and the entry SHALL pass.

#### Scenario: Threshold

- **WHEN** the ratio equals `min` or equals `max`
- **THEN** the entry SHALL be blocked.

#### Scenario: Pullback in favour of the trade

- **WHEN** the pullback mean force against the trade is negative and `min` is 0
- **THEN** the ratio SHALL be negative and the entry SHALL be blocked by `min`.

### Requirement: Anchor follow operand shape

An anchor follow reference SHALL be `{"anchor_follow": {"episode"}}`; `episode` is required and no other field is allowed.
`episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`. It SHALL be accepted as a side of a `ratio`, as the operand
of a `range` and of a `compare`, and rejected as the operand of a `change`.

#### Scenario: Malformed anchor follow

- **WHEN** an anchor follow names an undeclared episode, lacks `episode` or has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Anchor follow value

On each bar `t`, for the evaluated side with `g` = +1 on the long side and −1 on the short side, `P` the peak bar and `peak_price` the
peak price of the current touch of the episode (the high of bar `P` on the long side and the low on the short side), and `EMA` the
anchor EMA of the episode's stack, the value SHALL be `g · (EMA[t] − EMA[P]) ÷ g · (peak_price − EMA[P])`. It SHALL be missing when
the current touch has no valid wave, when the denominator is not greater than 0, or when `EMA[t]`, `EMA[P]` or `peak_price` is not
finite. A negative value SHALL stay a value. Bars after `t` SHALL NOT be read.

#### Scenario: Long side

- **WHEN** the side is long, `peak_price` 110, `EMA[P]` 100 and `EMA[t]` 104
- **THEN** the value SHALL be 0.4.

#### Scenario: Short side mirror

- **WHEN** the side is short, `peak_price` (the low of bar `P`) 90, `EMA[P]` 100 and `EMA[t]` 96
- **THEN** the value SHALL be 0.4.

#### Scenario: EMA moved away

- **WHEN** the side is long, `peak_price` 110, `EMA[P]` 100 and `EMA[t]` 98
- **THEN** the value SHALL be −0.2.

#### Scenario: No gap

- **WHEN** the denominator is 0 or negative
- **THEN** the value SHALL be missing.

### Requirement: Anchor follows the stack

The anchor EMA SHALL be the anchor (middle) EMA of the stack on which the episode is built, so that the value follows the stack
without a separate period in the operand.

#### Scenario: Two stacks

- **WHEN** one episode is declared on the stack 200 / 500 / 1000 and another on 500 / 1000 / 2000
- **THEN** the first SHALL read EMA500 and the second EMA1000.

### Requirement: Anchor follow filter

`range(anchor_follow)` with `bounds` `exclusive` and `empty: pass` SHALL block an entry when the value is not greater than `min` or
not less than `max` (both inclusive), each bound optional. A missing value SHALL pass.

#### Scenario: Threshold

- **WHEN** the value equals `min` or equals `max`
- **THEN** the entry SHALL be blocked.

#### Scenario: Missing value

- **WHEN** there is no wave or the denominator is not greater than 0
- **THEN** the entry SHALL pass.

### Requirement: Leg sum operand shape

A leg sum reference SHALL be `{"leg_sum": {"episode", "leg", "field"}}`; all three are required and no other field is allowed.
`episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`, `leg` SHALL be `impulse` or `pullback` and `field` SHALL be
`volume` or `open_interest`. It SHALL be accepted as a side of a `ratio`, as the operand of a `range`, of a `compare` and of a weighted vote input, and
rejected as the operand of a `change`.

#### Scenario: Malformed leg sum

- **WHEN** a leg sum names an undeclared episode, an unknown `leg` or `field`, lacks a required field or has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg sum value

On each bar `t` the legs SHALL be those of the leg mean operand: the impulse from `origin_bar` to `peak_bar` of the current touch
and the pullback from `peak_bar + 1` to `t`, both ends inclusive. The value SHALL be the sum of the field over the leg's bars and
SHALL be missing when the touch has no valid wave, when the leg is empty or when any bar of the leg has a non-finite field. Bars
after `t` SHALL NOT be read.

#### Scenario: Legs

- **WHEN** a wave has origin 10, peak 14 and `t` = 20
- **THEN** the impulse sum SHALL add bars 10 to 14 and the pullback sum bars 15 to 20.

#### Scenario: Peak bar

- **WHEN** `t` is the peak bar
- **THEN** the pullback sum SHALL be missing.

### Requirement: Volume sum ratio

`ratio(leg_sum(pullback, volume), leg_sum(impulse, volume))` SHALL be the pullback volume sum divided by the impulse volume sum. It
SHALL be missing when either sum is missing or the impulse sum is not greater than the ratio's `right_floor` (default 0). It SHALL
be the same on the long and the short side.

#### Scenario: Zero impulse volume

- **WHEN** the impulse leg has volume sum 0
- **THEN** the ratio SHALL be missing and a `range` with `empty: pass` SHALL not block the bar.

#### Scenario: Value

- **WHEN** the impulse sums to 2000 and the pullback to 100
- **THEN** the ratio SHALL be 0.05.

### Requirement: Own colour volume field

A leg sum MAY have `field` `own_color_volume`; a leg mean SHALL reject it. Its series on the evaluated side SHALL be `volume[u]` for a
bar whose candle has the leg's own colour and 0 otherwise. A non-finite `open`, `close` or `volume` on a leg bar SHALL make the value
missing.

#### Scenario: Missing input

- **WHEN** a pullback bar has a non-finite close
- **THEN** the own colour pullback sum SHALL be missing.

### Requirement: Own colour of a leg

On the impulse the own colour SHALL be `close > open` on the long side and `close < open` on the short side; on the pullback it
SHALL be `close < open` on the long side and `close > open` on the short side. A bar with `close = open` SHALL never count.

#### Scenario: Long pullback

- **WHEN** the side is long and the pullback has a red bar with volume 30, a green bar with volume 50 and a doji with volume 20
- **THEN** the own colour pullback sum SHALL be 30.

#### Scenario: Short impulse

- **WHEN** the side is short and an impulse bar closes below its open with volume 40
- **THEN** its volume SHALL count in the own colour impulse sum.

### Requirement: Own colour volume ratio

`ratio(leg_sum(pullback, own_color_volume), leg_sum(impulse, own_color_volume))` SHALL be missing when the impulse sum is not greater
than the ratio's `right_floor` (default 0) or either sum is missing. A pullback without a counter candle SHALL give 0, a value.

#### Scenario: Impulse without a with-trade candle

- **WHEN** no impulse bar of the long side closes above its open
- **THEN** the ratio SHALL be missing.

### Requirement: Leg top mean operand shape

A leg top mean reference SHALL be `{"leg_top_mean": {"episode", "leg", "field", "share"}}`; all four are required and no other field
is allowed. `episode` SHALL name a declared episode, `leg` SHALL be `impulse` or `pullback`, `field` SHALL be `volume` or `open_interest` and `share` a
finite number greater than 0 and at most 1. It SHALL be accepted where a leg sum is accepted and rejected as the operand of a `change`.

#### Scenario: Malformed leg top mean

- **WHEN** `share` is 0, above 1 or missing, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg top mean value

With the legs of the leg sum operand and `L` the number of bars of the leg, the value SHALL be the mean of the `k` largest field
values of the leg, `k = max(1, ceil(share · L))`, as research computes it in float64. It SHALL be missing when the touch has no valid wave, the leg is
empty or a bar of the leg has a non-finite field. Bars after `t` SHALL NOT be read.

#### Scenario: Top mean

- **WHEN** the pullback has 12 bars, `share` is 0.1 and its two largest volumes are 50 and 30
- **THEN** `k` SHALL be 2 and the value 40.

#### Scenario: Rounding of k

- **WHEN** the leg has 30 bars and `share` is 0.1
- **THEN** `k` SHALL be 3; with 11 bars it SHALL be 2.

### Requirement: Top volume ratio

`ratio(leg_top_mean(pullback), leg_top_mean(impulse))` SHALL be missing when either value is missing or the impulse value is not
greater than the ratio's `right_floor` (default 0).

#### Scenario: Zero impulse volume

- **WHEN** every impulse bar has volume 0
- **THEN** the ratio SHALL be missing.

### Requirement: Pullback depth operand shape

A pullback depth reference SHALL be `{"pullback_depth": {"episode", "touch"}}`; `episode` is required and SHALL name a declared
episode, `touch` is optional, `current` (default) or `previous`, and no other field is allowed. It SHALL be accepted where a leg sum
is accepted and rejected as the operand of a `change`.

#### Scenario: Malformed pullback depth

- **WHEN** `episode` is missing or undeclared, `touch` is neither `current` nor `previous`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Pullback depth value

On a bar `t` with a valid wave of the current touch, the value SHALL be `g · (peak_price − ext) / |peak_price − origin_price|`,
where `ext` is the lowest low of the bars `P..t` on the long side and the highest high on the short side, `g` is +1 long and −1
short. It SHALL be missing when the touch has no valid wave, the impulse height is 0 or a price of `P..t` is not finite. Bars after
`t` SHALL NOT be read.

#### Scenario: Long depth

- **WHEN** on the long side the origin price is 100, the peak price 110 and the lowest low of `P..t` is 103
- **THEN** the value SHALL be 0.7.

#### Scenario: Short depth

- **WHEN** on the short side the origin price is 110, the peak price 100 and the highest high of `P..t` is 104
- **THEN** the value SHALL be 0.4.

### Requirement: Previous pullback depth value

With `touch: previous`, on a bar `t` whose current touch has a valid wave and a previous touch row in the same episode, the value
SHALL be `g · (P0_price − ext0) / |P0_price − S0_price|`, where `S0`, `P0` are the origin and peak of the previous touch row and
`ext0` is the lowest low (long) or highest high (short) of the bars `P0..S*`, `S*` the origin of the current touch.

#### Scenario: Previous depth

- **WHEN** on the long side the previous origin price is 100, the previous peak price 110 and the lowest low of `P0..S*` is 108
- **THEN** the value SHALL be 0.2.

### Requirement: Previous pullback depth missing cases

The previous depth SHALL be missing on the first touch of an episode, when `S* ≤ P0`, when the previous impulse height is 0 or a
price of `P0..S*` is not finite. Bars after `t` SHALL NOT be read.

#### Scenario: Zero previous height

- **WHEN** the previous origin and peak prices are equal
- **THEN** the value SHALL be missing.

#### Scenario: First touch

- **WHEN** the current touch is the first of its episode
- **THEN** the value SHALL be missing.

### Requirement: Depth ratio to the previous pullback

`ratio(pullback_depth, pullback_depth touch previous, right_floor)` SHALL be missing when either value is missing or the previous
depth is not greater than `right_floor`.

#### Scenario: Three times deeper

- **WHEN** the current depth is 0.6 and the previous 0.2 with `right_floor` 1e-6
- **THEN** the ratio SHALL be 3.

### Requirement: Leg speed operand shape

A leg speed reference SHALL be `{"leg_speed": {"episode", "leg"}}`; both are required and no other field is allowed. `episode` SHALL
name a declared episode and `leg` SHALL be `impulse` or `pullback`. It SHALL be accepted where a leg sum is accepted and rejected as
the operand of a `change`.

#### Scenario: Malformed leg speed

- **WHEN** `leg` is missing or neither `impulse` nor `pullback`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg speed value

On a bar `t` with a valid wave of the current touch, the impulse value SHALL be `|peak_price − origin_price| / (P − S* + 1)` and the
pullback value `|peak_price − close[t]| / (t − P + 1)`. It SHALL be missing when the touch has no valid wave or an input price is not
finite. Bars after `t` SHALL NOT be read.

#### Scenario: Pullback three times faster

- **WHEN** the impulse rises 10 over the bars `S*..P` (10 bars) and the close of `t` is 6 below the peak price with `t − P + 1 = 2`
- **THEN** the impulse value SHALL be 1, the pullback value 3 and `ratio(pullback, impulse)` 3.

#### Scenario: Zero impulse height

- **WHEN** the origin and peak prices are equal
- **THEN** the impulse value SHALL be 0 and `ratio(pullback, impulse)` missing.

### Requirement: Impulse ATR operand shape

An impulse ATR reference SHALL be `{"impulse_atr": {"episode", "atr"}}`; both are required and no other field is allowed. `episode`
SHALL name a declared episode and `atr` SHALL be a feature request of kind `atr` on the base timeframe. It SHALL be accepted where a
leg sum is accepted and rejected as the operand of a `change`.

#### Scenario: Malformed impulse ATR

- **WHEN** `atr` is missing, of another kind or on another timeframe, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Impulse ATR value

On a bar `t` with a valid wave of the current touch, the value SHALL be `|peak_price − origin_price| / atr[P]`. It SHALL be missing
when the touch has no valid wave, a price is not finite, or `atr[P]` is not finite or not above 0. Bars after `t` SHALL NOT be read.

#### Scenario: Twelve average candles

- **WHEN** the impulse height is 6 and the ATR on the peak bar is 0.5
- **THEN** the value SHALL be 12 on every bar of that touch.

#### Scenario: ATR not yet defined

- **WHEN** the peak bar lies before the first full ATR window
- **THEN** the value SHALL be missing.

### Requirement: Leg bars operand shape

A leg bars reference SHALL be `{"leg_bars": {"episode", "leg"}}`; both are required and no other field is allowed. `episode` SHALL
name a declared episode and `leg` SHALL be `impulse` or `pullback`. It SHALL be accepted where a leg sum is accepted and rejected as
the operand of a `change`.

#### Scenario: Malformed leg bars

- **WHEN** `leg` is missing or neither `impulse` nor `pullback`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg bars value

On a bar `t` with a valid wave of the current touch, the impulse value SHALL be `P − S* + 1` and the pullback value `t − P + 1`. It
SHALL be missing when the touch has no valid wave. Bars after `t` SHALL NOT be read.

#### Scenario: Pullback ten times longer

- **WHEN** the impulse spans bars 100..109 and the evaluated bar is 199
- **THEN** the impulse value SHALL be 10, the pullback value 100 and `ratio(pullback, impulse)` 10.

### Requirement: Forming candle operand shape

A forming candle reference SHALL be `{"forming_candle": {"episode", "timeframe", "atr"}}`; all are required and no other field is
allowed. `episode` SHALL name a declared episode; `timeframe` SHALL be longer than the base timeframe, a multiple of it and a divisor
of a day; `atr` SHALL be a feature request of kind `atr_wilder` on the same timeframe. It SHALL be accepted where a leg sum is
accepted and rejected as the operand of a `change`.

#### Scenario: Malformed forming candle

- **WHEN** `atr` is missing, of another kind or on another timeframe, `timeframe` is the base timeframe, or a field is unknown
- **THEN** static validation SHALL reject the spec.

### Requirement: Forming candle value

On a bar `t` with a valid wave of the current touch, the value SHALL be `g · (close[t] − open) / atr`, where `open` is the open of
the first base bar of the candle of `timeframe` that contains `t`, `atr` is the ATR of the last completed candle before it, and `g`
is +1 on the long side and −1 on the short side. It SHALL be missing without a valid wave, or when a price is not finite or the ATR
is not finite or not above 0. Bars after `t` SHALL NOT be read.

#### Scenario: Day moved against a long

- **WHEN** the day opened at 100, the close of `t` is 98 and the ATR of the previous day is 4, on the long side
- **THEN** the value SHALL be −0.5, and on the short side 0.5.

#### Scenario: ATR not yet defined

- **WHEN** fewer completed candles than the ATR period precede the candle of `t`
- **THEN** the value SHALL be missing.

### Requirement: Leg efficiency operand shape

A leg efficiency reference SHALL be `{"leg_efficiency": {"episode", "leg"}}`; both are required and no other field is allowed.
`episode` SHALL name a declared episode and `leg` SHALL be `impulse` or `pullback`. It SHALL be accepted where a leg sum is accepted
and rejected as the operand of a `change`.

#### Scenario: Malformed leg efficiency

- **WHEN** `leg` is missing or neither `impulse` nor `pullback`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg efficiency value

On a bar `t` with a valid wave of the current touch, the value SHALL be `|close[z] − close[a]| / Σ |close[k] − close[k−1]|` over
`k = a+1..z`, with `a = S*, z = P` for the impulse and `a = P, z = t` for the pullback. It SHALL be missing without a valid wave,
when `z ≤ a`, when the sum is 0, or when a close of `[a, z]` is not finite. Bars after `t` SHALL NOT be read.

#### Scenario: Straight pullback, crooked impulse

- **WHEN** the impulse closes go 100, 103, 101, 104 and the pullback closes go 104, 102, 100
- **THEN** the impulse value SHALL be 0.5, the pullback value 1 and `ratio(pullback, impulse)` 2.

#### Scenario: Pullback of one bar

- **WHEN** the evaluated bar is the peak bar
- **THEN** the pullback value SHALL be missing.

### Requirement: Leg change operand shape

A leg change reference SHALL be `{"leg_change": {"episode", "leg", "field", "touch"}}`; `episode` (a declared episode), `leg`
(`impulse` | `pullback`) and `field` (`close` | `open_interest`) are required, `touch` (`current` | `previous`) defaults to
`current` and `previous` SHALL be allowed only with `impulse`. No other field is allowed.

#### Scenario: Malformed leg change

- **WHEN** `field` is `volume`, or `touch` is `previous` with `leg` `pullback`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg change placement

A leg change SHALL be accepted where a leg sum is accepted and rejected as the operand of a `change`.

#### Scenario: Leg change inside change

- **WHEN** a `change` operand is a leg change
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg change value

On a bar `t` the value SHALL be `100 * (x[end] / x[begin] - 1)` of the base-bar field `x`, with `(begin, end)` `(S*, P)` of the
current touch for `impulse`, `(P, t)` for `pullback`, and `(S*, P)` of the previous touch of the same episode for `impulse` with
`touch` `previous`. It SHALL be missing when there is no valid wave or no previous touch, when either value is not finite, or when
`x[begin] <= 0`. Bars after `t` SHALL NOT be read.

#### Scenario: Open interest falls over the impulse

- **WHEN** the open interest is 1000 at `S*` and 940 at `P`
- **THEN** the impulse value over `open_interest` SHALL be −6 on every bar of that touch.

#### Scenario: Missing open interest at the peak

- **WHEN** the bar `P` has no open interest
- **THEN** the impulse value over `open_interest` SHALL be missing.

