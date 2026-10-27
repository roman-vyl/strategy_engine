## MODIFIED Requirements

### Requirement: Weighted vote inputs

Each input SHALL have:

- `input_id`, unique within the setup and without `/`;
- exactly one of:
  - `operand` together with `direction` (`at_most` or `at_least`) and `steps`, a non-empty list;
  - `operand` together with `curve` (see "Curve input"), without `direction` and `steps`;
  - `count` of the shape `{"of": [<predicate>, ...]}`, a non-empty list, with `steps` and without `direction`;
- optionally `short` (see "Short operand") and `when` (see "Input gate").

The `operand` SHALL be any operand the predicate layer accepts as the operand of a `range`, validated by that layer. Each element
of `count.of` SHALL be a predicate of the layer, validated by that layer.

#### Scenario: Operand not accepted by the layer

- **WHEN** an input operand is a `change` predicate or names an undeclared episode
- **THEN** static validation SHALL reject the spec with the predicate layer's error.

#### Scenario: Curve with steps

- **WHEN** an input has `curve` and also `steps` or `direction`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Curve in a veto voter

- **WHEN** a voter with `role` `veto` has an input with `curve`
- **THEN** static validation SHALL reject the spec.

### Requirement: Input and voter weight

- The weight of a step input on `t` SHALL be the largest `weight` among its crossed steps, or 0 when none is crossed.
- The weight of a curve input on `t` SHALL be its curve weight (see "Curve weight").
- An input whose gate is closed on `t` (see "Input gate") SHALL weigh 0 and SHALL NOT veto.
- An input SHALL veto on `t` when any crossed step is a veto step.
- The weight of a voter SHALL be the largest weight among its inputs, so a voter with several inputs is their OR.
- A voter SHALL veto when any of its inputs vetoes.
- The order of steps, inputs and voters SHALL NOT change any weight, veto, score or mask. Declared order SHALL matter only for
  `blocked_by` in the evidence.

#### Scenario: Deepest step on a monotone ladder

- **WHEN** an `at_most` input has steps (0.8, 0.1), (0.4, 0.3), (0.1, 0.33) and the value is 0.3
- **THEN** the input weight SHALL be 0.3.

#### Scenario: Two inputs of one voter

- **WHEN** a voter has two inputs with weights 0.2 and 0.3 on `t`
- **THEN** the voter weight SHALL be 0.3, not 0.5.

#### Scenario: OR of two curve inputs

- **WHEN** a voter has curve inputs kI (k 0.3, e_v 16) and O1 (k 0.6, e_v 20) with weights 0.41 and 0.95 on `t`
- **THEN** the voter weight SHALL be 0.95.

#### Scenario: Unsorted steps

- **WHEN** the same steps are listed in another order
- **THEN** every weight, veto and mask SHALL be unchanged.

### Requirement: Exact score comparison

- Without curve inputs, sums of weights and the comparison with the threshold SHALL be exact on integers in units of 10⁻⁹.
- With at least one curve input in the setup, the score SHALL be the exact rational sum of the voter weights, each curve weight taken
  at the exact value of its float64 and each step weight at its exact decimal value; the bar SHALL be blocked when this sum is
  ≥ `threshold` compared exactly.
- In both cases the result SHALL NOT depend on the order of the voters.
- Levels are compared with operand values in the operands' own floating-point arithmetic.
- In the evidence, `score` SHALL be the exact sum converted to the nearest float.

#### Scenario: Exact sum on the threshold

- **WHEN** `threshold` is 0.75 and three voters have weights 0.3, 0.25 and 0.2 on `t`, in any declared order
- **THEN** `score` SHALL equal the threshold exactly and the bar SHALL be blocked.

#### Scenario: Classic binary case

- **WHEN** `threshold` is 0.8 and two voters have weights 0.1 and 0.7
- **THEN** the bar SHALL be blocked, although the binary floating-point sum 0.1 + 0.7 is 0.7999999999999999.

#### Scenario: Curve weights in any order

- **WHEN** a setup has curve voters and the voters are listed in another order
- **THEN** `score` and the mask SHALL be identical on every bar.

### Requirement: Weighted vote evidence

The `SetupMask.trace` SHALL contain, per evaluated side, on every bar:

- `input:<input_id>:value`: the operand value of the side, or for a `count` input the count; null where missing;
- `input:<input_id>:excess` for a curve input: the curve value `e` (0 where the value is missing or the gate is closed);
- `input:<input_id>:when` for an input with `when`: whether the gate is open;
- `input:<input_id>:weight` and `input:<input_id>:veto`;
- `voter:<voter_id>:weight` and `voter:<voter_id>:veto`;
- `score`;
- `blocked_by` (see "Block attribution").

#### Scenario: Which input gave the weight

- **WHEN** a voter has inputs with weights 0.2 and 0.3 on `t`
- **THEN** the trace SHALL show both input weights and the voter weight 0.3.

#### Scenario: Closed gate in the trace

- **WHEN** an input's gate is closed on `t` and its operand value is −0.4
- **THEN** the trace SHALL show value −0.4, `when` false and weight 0.

## ADDED Requirements

### Requirement: Curve input

`curve` SHALL have exactly `grid`, `excess`, `k` and `e_v`:

- `grid` and `excess`: lists of finite numbers of the same length, at least 2; `grid` strictly increasing;
- `k` and `e_v`: finite numbers greater than 0;
- `k · max(0, max(excess))` ≤ 700 and `k · e_v` ≤ 700;
- booleans SHALL NOT be accepted as numbers; unknown keys SHALL be rejected;
- curve numbers have no decimal-digit limit and no default.

#### Scenario: Grid not increasing

- **WHEN** `grid` has two equal or decreasing neighbours
- **THEN** static validation SHALL reject the spec.

#### Scenario: Overflowing exponent

- **WHEN** `k` is 50 and the largest excess is 20
- **THEN** static validation SHALL reject the spec.

### Requirement: Curve weight

On bar `t` of a side, with operand value `x` of that side and an open gate:

- `x` missing or non-finite: excess 0 and weight 0;
- otherwise excess `e` = linear interpolation of `x` over (`grid`, `max(excess_i, 0)`), with the nodes clipped at 0 before
  interpolation, the first node's value left of `grid`, the last node's value right of it (as `numpy.interp`);
- weight `w = (exp(k · e) − 1) / (exp(k · e_v) − 1)` in float64, computed in this form.

There SHALL be no cap: `e > e_v` gives `w > 1`.

#### Scenario: Value between nodes

- **WHEN** `grid` is [0, 1], `excess` is [16, 0], `k` 0.15, `e_v` 16 and `x` is 0.5
- **THEN** `e` SHALL be 8 and `w` SHALL be (exp(1.2) − 1)/(exp(2.4) − 1).

#### Scenario: Negative node clipped first

- **WHEN** `grid` is [0, 1], `excess` is [−4, 4] and `x` is 0.5
- **THEN** `e` SHALL be 2 (between 0 and 4), not 0.

#### Scenario: Right of the grid

- **WHEN** the last node of `excess` is 0.104 and `x` is greater than the last grid point
- **THEN** `e` SHALL be 0.104 and the weight SHALL be greater than 0.

#### Scenario: Missing value

- **WHEN** the operand value is missing on `t`
- **THEN** the input weight SHALL be 0.

### Requirement: Short operand

An input with `operand` MAY carry `short` of the shape `{"operand": <operand>}`. On the short side the input SHALL read that operand
instead of `operand`; the long side SHALL read `operand`. The short operand SHALL be validated by the predicate layer like `operand`.
`short` SHALL NOT be accepted on a `count` input.

#### Scenario: Weekly body our way

- **WHEN** `operand` is the 1w `candle_body_atr` feature and `short.operand` is its `difference` from `const` 0
- **THEN** on a short the input value SHALL be the negated body and on a long the body.

### Requirement: Input gate

An input MAY carry `when`, a non-empty list of predicates of the predicate layer, validated by that layer (each with its own
optional `short` override). On bar `t` of a side the gate SHALL be open when every predicate is True on `t` for that side. When the
gate is closed the input SHALL weigh 0 and SHALL NOT veto. A predicate over a missing operand is False by the layer's rules.

#### Scenario: D1v gate closed

- **WHEN** an input over the forming 1d candle has `when` [yesterday body ≥ 1, yesterday close position ≥ 0.85] and yesterday's body
  is 0.7
- **THEN** the input SHALL weigh 0 whatever today's value.

#### Scenario: Gate on a step veto

- **WHEN** a step input with a veto step has a closed gate and its value crosses the veto step
- **THEN** it SHALL NOT veto.

### Requirement: Specs without the new keys are unchanged

A spec whose vote inputs have no `curve`, `short` or `when` SHALL produce the same masks, evidence and node identities as before
this change.

#### Scenario: Vote B config

- **WHEN** the existing vote B config is evaluated
- **THEN** masks, trace series and identities SHALL be byte for byte those of main before this change.
