# ema-pullback-weighted-vote-setup-v1 Specification

## Purpose
`weighted_vote_setup` blocks an entry when any veto step is crossed or the exact sum of voter weights reaches the threshold.
Voters read existing operands or counts of predicates. An input's ladder is read as steps or as points joined by straight lines,
and its value is the weight itself or turned into a weight by an exponent. Every level, weight, veto, exponent and threshold
comes from the strategy spec, with no defaults and no calibration inside the Engine. The vote knows no trade side.

## Requirements
### Requirement: Weighted vote setup is an ordinary setup

`weighted_vote_setup` SHALL be a setup component. It SHALL produce an ordinary `SetupMask` with local, context-gated and final
masks, MAY declare `context_consumption`, and its final mask SHALL be AND-composed with the other declared setups by the existing
setup composition. It SHALL NOT be accepted as a child of `composite_setup`.

#### Scenario: Vote alongside other setups

- **WHEN** a spec declares `untouched_anchor_setup` and a `weighted_vote_setup`
- **THEN** `setups_ok` SHALL equal the AND of both final masks.

#### Scenario: Vote inside a composite is rejected

- **WHEN** a `composite_setup` child has `component_id` `weighted_vote_setup`
- **THEN** static validation SHALL reject the spec.

### Requirement: Weighted vote parameters

`params` SHALL contain exactly `threshold` and `voters`.

- `threshold` SHALL be a number greater than 0 (see "Exact decimal weights" for its precision).
- `voters` SHALL be a non-empty list. Each voter SHALL have exactly:
  - `voter_id`: unique within the setup and without `/`;
  - `role`: `vote` or `veto`;
  - `inputs`: a non-empty list.
- A voter with `role` `veto` SHALL have only veto steps.
- Unknown keys SHALL be rejected at every level.

#### Scenario: Missing threshold

- **WHEN** `params` has `voters` but no `threshold`, or a `threshold` that is 0, negative or non-finite
- **THEN** static validation SHALL reject the spec.

#### Scenario: Veto voter with a weight

- **WHEN** a voter has `role` `veto` and one of its steps has a `weight`
- **THEN** static validation SHALL reject the spec.

### Requirement: Weighted vote inputs

Each input SHALL have:

- `input_id`, unique within the setup and without `/`;
- `steps`, a non-empty list;
- exactly one of:
  - `operand` together with `direction` (`at_most` or `at_least`);
  - `operand` together with `between: "linear"`, without `direction`;
  - `count` of the shape `{"of": [<predicate>, ...]}`, a non-empty list, without `direction`;
- optionally `between` (`step` or `linear`, see "Linear ladder value") and `weighting` (see "Exponent weighting parameters").

The vote SHALL know no trade side: it SHALL read the operand value of the evaluated side as the operand gives it. Giving the value
"our way" (sign, side-specific gates) is the operand's responsibility.

The `operand` SHALL be any operand the predicate layer accepts as the operand of a `range`, validated by that layer. Each element
of `count.of` SHALL be a predicate of the layer, validated by that layer.

#### Scenario: Operand not accepted by the layer

- **WHEN** an input operand is a `change` predicate or names an undeclared episode
- **THEN** static validation SHALL reject the spec with the predicate layer's error.

#### Scenario: Side keys in the vote

- **WHEN** an input carries `short` or `when`
- **THEN** static validation SHALL reject the spec as an unknown field.

#### Scenario: Linear ladder with a direction

- **WHEN** an input has `between: "linear"` and also `direction`
- **THEN** static validation SHALL reject the spec.

### Requirement: Weighted vote steps

- Each step SHALL have a finite `level` and exactly one of:
  - `weight`: a number ≥ 0 (see "Exact decimal weights" for its precision);
  - `veto`: the literal `true`.
- Levels SHALL be unique within an input. For a `count` input the levels SHALL be integers from 1 to the length of `of`.
- Booleans SHALL NOT be accepted as numbers in `threshold`, `level` or `weight`.

#### Scenario: Step with both weight and veto

- **WHEN** a step has both `weight` and `veto`, or neither
- **THEN** static validation SHALL reject the spec.

#### Scenario: Boolean in a numeric field

- **WHEN** `threshold`, a `level` or a `weight` is `true` or `false`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Count level out of range

- **WHEN** a `count` input has three predicates and a step level of 4 or 0
- **THEN** static validation SHALL reject the spec.

### Requirement: Step crossing

On bar `t` of the evaluated side a step SHALL be crossed:

- for an `operand` input with `direction` `at_most`, when the operand value is finite and `value ≤ level`;
- for an `operand` input with `direction` `at_least`, when the operand value is finite and `value ≥ level`;
- for a `count` input, when the number of predicates of `of` that are True on `t` is `≥ level`.

A missing or non-finite operand value SHALL cross no step.

#### Scenario: Value exactly on a level

- **WHEN** an `at_most` input has a step at level 0.4 and the value is 0.4
- **THEN** that step SHALL be crossed.

#### Scenario: Missing value

- **WHEN** the operand value is missing on `t`
- **THEN** no step of the input SHALL be crossed and the input SHALL contribute weight 0 and no veto.

### Requirement: Count input has no missing state

A `count` input SHALL have no missing state. Each predicate of `of` is the boolean mask of the predicate layer, so on a bar where its
operand is missing it is False, or True for a `range` with `empty: pass`, by the requirement "Non-finite values are not satisfied".
The count SHALL be the number of True predicates on `t`.

#### Scenario: Count with a missing operand

- **WHEN** `count.of` is [A, B, C], A and C are True on `t`, B is a `range` with the default `empty` whose operand is missing, and the
  step level is 2
- **THEN** B SHALL be False, the count SHALL be 2 and the step SHALL be crossed
- **AND** if B instead declares `empty: pass`, the count SHALL be 3.

### Requirement: Input and voter weight

- The ladder value of a step input on `t` SHALL be the largest `weight` among its crossed steps, or 0 when none is crossed; of a linear
  input, its value by "Linear ladder value".
- The weight of an input SHALL be its ladder value without `weighting`, or the exponent of it by "Exponent weight".
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

#### Scenario: OR of two exponent inputs

- **WHEN** a voter has inputs kI (k 0.3, e_v 16) and O1 (k 0.6, e_v 20) with weights 0.41 and 0.95 on `t`
- **THEN** the voter weight SHALL be 0.95.

#### Scenario: Unsorted steps

- **WHEN** the same steps are listed in another order
- **THEN** every weight, veto and mask SHALL be unchanged.

### Requirement: Score and block

On each bar `t` of the evaluated side:

- `score[t]` SHALL be the sum of the voter weights in the exact decimal arithmetic of the requirement "Exact decimal weights";
- the bar SHALL be blocked when any voter vetoes or `score[t] ≥ threshold`, compared exactly in the same arithmetic;
- the local mask SHALL be True exactly where the bar is not blocked.
- No weight, level or threshold SHALL have a default in the Engine.

#### Scenario: Chorus of weak voters

- **WHEN** `threshold` is 0.75 and three voters have weights 0.3, 0.25 and 0.2 on `t`, with no veto
- **THEN** `score` SHALL be 0.75 and the bar SHALL be blocked.

#### Scenario: Below the threshold

- **WHEN** the voter weights sum to 0.74 with no veto
- **THEN** the bar SHALL NOT be blocked.

#### Scenario: Veto alone

- **WHEN** one voter vetoes on `t` and every weight is 0
- **THEN** the bar SHALL be blocked.

#### Scenario: Side symmetry

- **WHEN** the same setup is evaluated on the long and the short side
- **THEN** each side SHALL use its own operand values with the same steps and threshold.

### Requirement: Exact decimal weights

Weights and the threshold SHALL be exact decimal numbers.

- The value of each one SHALL be the decimal number of the shortest representation that round-trips the parsed number (Python `repr`).
- It SHALL have at most 9 digits after the decimal point. A value with more SHALL be rejected by static validation.

#### Scenario: Too many digits

- **WHEN** a weight is 0.1234567891
- **THEN** static validation SHALL reject the spec.

### Requirement: Exact score comparison

- Without exponent or linear inputs, sums of weights and the comparison with the threshold SHALL be exact on integers in units of
  10⁻⁹.
- With at least one exponent or linear input in the setup, the block SHALL be decided on the exact rational sum of the voter weights,
  each float weight taken at the exact value of its float64 and each step weight at its exact decimal value, compared with
  `threshold` exactly.
- In both cases the result SHALL NOT depend on the order of the voters.
- Levels are compared with operand values in the operands' own floating-point arithmetic.
- In the evidence, `score` SHALL be the exact sum converted to the nearest float without exponent or linear inputs, and the float64 sum
  of the voter weights with them.

#### Scenario: Exact sum on the threshold

- **WHEN** `threshold` is 0.75 and three voters have weights 0.3, 0.25 and 0.2 on `t`, in any declared order
- **THEN** `score` SHALL equal the threshold exactly and the bar SHALL be blocked.

#### Scenario: Classic binary case

- **WHEN** `threshold` is 0.8 and two voters have weights 0.1 and 0.7
- **THEN** the bar SHALL be blocked, although the binary floating-point sum 0.1 + 0.7 is 0.7999999999999999.

#### Scenario: Float and decimal weights on the threshold

- **WHEN** `threshold` is 0.8, a step input weighs 0.7 and a linear input 0.1 (float64)
- **THEN** the bar SHALL be blocked, because the exact sum exceeds 0.8, although the float64 sum is 0.7999999999999999.

#### Scenario: Exponent weights in any order

- **WHEN** a setup has exponent inputs and the voters are listed in another order
- **THEN** `score` and the mask SHALL be identical on every bar.

### Requirement: Weighted vote evidence

The `SetupMask.trace` SHALL contain, per evaluated side, on every bar:

- `input:<input_id>:value`: the operand value of the side, or for a `count` input the count; null where missing;
- `input:<input_id>:level_value` for an input with `weighting`: the ladder value before weighting;
- `input:<input_id>:weight` and `input:<input_id>:veto`;
- `voter:<voter_id>:weight` and `voter:<voter_id>:veto`;
- `score`;
- `blocked_by` (see "Block attribution").

#### Scenario: Which input gave the weight

- **WHEN** a voter has inputs with weights 0.2 and 0.3 on `t`
- **THEN** the trace SHALL show both input weights and the voter weight 0.3.

#### Scenario: Level value in the trace

- **WHEN** an exponent input has ladder value 8 on `t`, `k` 0.15 and `e_v` 16
- **THEN** the trace SHALL show `level_value` 8 and the weight (exp(1.2) − 1)/(exp(2.4) − 1).

### Requirement: Block attribution

`blocked_by` SHALL be, on every bar:

- `veto:<voter_id>` of the first vetoing voter in declared order;
- otherwise `score` when `score ≥ threshold`;
- otherwise null.

The trading decision does not depend on declared order. Only `blocked_by` does: when several voters veto, it names the first one in
declared order.

#### Scenario: Reason of a block

- **WHEN** voters `alpha` and `gamma` veto on `t`
- **THEN** `blocked_by` SHALL be `veto:alpha` when `alpha` is declared before `gamma`
- **AND** the mask SHALL be the same if their order is swapped.

### Requirement: No lookahead

The weighted vote on bar `t` SHALL read only what its inputs read on `t`. Changing bars after `t` SHALL NOT change any weight, veto,
score or mask on `t`.

#### Scenario: Truncated history

- **WHEN** the bars after `t` are removed or altered
- **THEN** every trace series and the mask on bars `≤ t` SHALL be unchanged.

### Requirement: Exponent weighting parameters

An input MAY carry `weighting` of the shape `{"exponent": {"k": k, "e_v": e_v}}`:

- `k` and `e_v` SHALL be finite numbers greater than 0, not booleans; unknown keys SHALL be rejected; no defaults;
- `k · (largest step weight)` ≤ 700 and `k · e_v` ≤ 700;
- the input SHALL belong to a `vote` voter and SHALL have no veto step.

#### Scenario: Exponent on a veto voter

- **WHEN** an input with `weighting` belongs to a voter with `role` `veto`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Overflowing exponent

- **WHEN** `k` is 50 and the largest step weight is 20
- **THEN** static validation SHALL reject the spec.

### Requirement: Exponent weight

With ladder value `x` on `t`, the weight of an exponent input SHALL be `(exp(k · x) − 1) / (exp(k · e_v) − 1)` in float64, computed in
this form. There SHALL be no cap: `x > e_v` gives a weight above 1; `x = 0` gives 0.

#### Scenario: Weight at e_v

- **WHEN** `k` is 0.15, `e_v` 16 and the ladder value is 16
- **THEN** the weight SHALL be 1.

#### Scenario: Weight in the middle

- **WHEN** `k` is 0.15, `e_v` 16 and the ladder value is 8
- **THEN** the weight SHALL be (exp(1.2) − 1)/(exp(2.4) − 1).

### Requirement: Linear ladder steps

An input with `between: "linear"` SHALL have at least 2 steps, all with `weight` (no veto step), levels unique, and no `direction`.
`between` absent or `step` SHALL keep the step crossing of "Step crossing".

#### Scenario: Linear ladder with a veto step

- **WHEN** an input has `between: "linear"` and a step with `veto: true`
- **THEN** static validation SHALL reject the spec.

### Requirement: Linear ladder value

On `t`, with a finite operand value `x`, the ladder value of a linear input SHALL be the linear interpolation of `x` over its points
(`level`, `weight`) sorted by level, the value of the lowest level for `x` below it and the value of the highest level for `x` above
it. A missing or non-finite value SHALL give ladder value 0.

#### Scenario: Between two points

- **WHEN** the steps are (0.6, 16) and (0.7, 0) and the value is 0.65
- **THEN** the ladder value SHALL be 8.

#### Scenario: Outside the points

- **WHEN** the highest level is 1.0 with value 0.104 and the value is 1.2
- **THEN** the ladder value SHALL be 0.104.

#### Scenario: Missing value

- **WHEN** the operand value is missing on `t`
- **THEN** the ladder value and the weight SHALL be 0.

### Requirement: Specs without the new keys are unchanged

A spec whose vote inputs have no `between` or `weighting` SHALL produce the same masks, evidence and node identities
as before this change.

#### Scenario: Vote B config

- **WHEN** the existing vote B config is evaluated
- **THEN** masks, trace series and identities SHALL be those of main before this change.

