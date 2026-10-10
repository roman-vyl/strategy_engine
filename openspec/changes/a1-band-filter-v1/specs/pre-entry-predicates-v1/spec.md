## MODIFIED Requirements

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
"Segment operand shape", "Segment points", "Segment value" and "Ratio operand".

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

- **WHEN** a segment over `macd_hist` with `select` positive is
  evaluated for the short side
- **THEN** it SHALL aggregate `max(−h, 0)` over the segment of the
  short side's episode.

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

## ADDED Requirements

### Requirement: Segment operand shape

A segment reference SHALL be `{"segment": {"episode", "of", "from", "to", "select", "aggregate"}}`, every field required and
no other field allowed:

- `episode`: an episode declared in `raw_spec.ema_stack_episode`;
- `of`: a feature reference resolved by the canonical feature-kind contract, on the base timeframe;
- `from` → `to`: `origin → peak`, `peak → current` or `origin → current`;
- `select`: `all`, `positive` or `negative_abs`;
- `aggregate`: `sum`, `mean_per_bar` or `max`.

#### Scenario: Malformed segment

- **WHEN** a segment names an undeclared episode, an unknown kind, a pair such as `current → peak`, an unknown `select` or
  `aggregate`, a missing field, or an unknown field such as `window`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Higher-timeframe series

- **WHEN** `of` is on a timeframe other than the base timeframe
- **THEN** evaluation SHALL fail closed.

### Requirement: Segment points

On base bar `t`, for the evaluated side, the points SHALL come from the current touch `m = touch_number[t]` of the episode:
`origin` is the origin bar `S*` of wave `m`, `peak` its peak bar `P`, `current` is `t`. The segment SHALL be the bars `a..b`
of the chosen pair, both ends inclusive, with `bars = b − a + 1`. Only bars `≤ t` SHALL be read and the operand SHALL have
no lookback window of its own.

#### Scenario: Peak bar belongs to both legs

- **WHEN** one segment is `origin → peak` and another `peak → current` on the same bar
- **THEN** bar `P` SHALL be counted in both.

#### Scenario: Before the first touch

- **WHEN** the episode is active and `touch_number` is 0, or the episode is inactive or censored
- **THEN** the segment SHALL be missing.

### Requirement: Segment value

With `x` the plan column of `of`, `y = x` for long and `y = −x` for short, each bar SHALL contribute `y` (`all`),
`max(y, 0)` (`positive`) or `max(−y, 0)` (`negative_abs`). `sum` SHALL add these over `a..b`, `mean_per_bar` SHALL divide
that sum by `bars`, and `max` SHALL take their largest value. The value SHALL be missing when any `x` on `a..b` is
non-finite. Cost SHALL NOT depend on segment lengths beyond a logarithmic factor for `max`.

#### Scenario: Pullback strength against the trade

- **WHEN** a segment is `macd_hist` (5m, 48-78-48), `peak → current`, `negative_abs`, `mean_per_bar`, long side, bar `t`,
  current touch `m ≥ 1`
- **THEN** its value SHALL be `Σ max(−h, 0)` over bars `P_m..t` divided by `t − P_m + 1`.

#### Scenario: Non-finite value inside the segment

- **WHEN** the series is non-finite on any bar of the segment
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
