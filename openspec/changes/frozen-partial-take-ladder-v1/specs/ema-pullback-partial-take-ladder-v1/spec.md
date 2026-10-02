# Spec Delta

## Purpose

Define the frozen partial take ladder of the EMA Pullback exit policy:
the partial take components, the canonical meaning of a ladder of
entry-frozen partial takes plus the final take, its static validation,
and the stable identity of each partial take.

## ADDED Requirements

### Requirement: Partial take components

The exit policy SHALL accept two partial take components in
`always_on` and in each profile, each with `exit_kind: "partial_take"`:

- `pct_partial_take` with `pct` and `fraction_of_initial`;
- `atr_partial_take` with `distance{timeframe, period, multiplier}` and
  `fraction_of_initial`.

Any other `exit_kind` on these components, or `"partial_take"` on any
other component, SHALL be rejected.

#### Scenario: Partial take rule is accepted

- **WHEN** a spec's `always_on` exits contain
  `{"instance_id": "pt_1pct", "component_id": "pct_partial_take",
  "exit_kind": "partial_take", "pct": 0.01, "fraction_of_initial": 0.25}`
- **THEN** the spec SHALL validate
- **AND** the rule SHALL be a partial take with `take_id` `pt_1pct`.

#### Scenario: Mismatched exit kind is rejected

- **WHEN** an `atr_partial_take` rule declares `exit_kind: "take_profit"`
- **OR** an `atr_take_profit` rule declares `exit_kind: "partial_take"`
- **THEN** validation SHALL fail with an exit-kind mismatch error.

### Requirement: Partial take level

A partial take level SHALL be a profit-side distance from the entry
price, frozen when the entry is planned:

- `pct_partial_take`: relative distance `pct`;
- `atr_partial_take`: absolute distance `multiplier × ATR(timeframe,
  period)` on the entry bar, the same formula as `atr_take_profit`.

The level SHALL NOT be recalculated after entry.

#### Scenario: Pct level on both sides

- **WHEN** a `pct_partial_take` with `pct` 0.01 applies to an entry at
  price 100
- **THEN** its level SHALL be 101 for a long entry
- **AND** 99 for a short entry.

#### Scenario: ATR level matches the take formula

- **WHEN** an `atr_partial_take` and an `atr_take_profit` share the
  same timeframe, period and multiplier
- **THEN** both SHALL produce the same distance on every bar.

### Requirement: Fraction of initial quantity

`fraction_of_initial` SHALL be the share of the initial position
quantity that the partial take closes. It SHALL NOT be a share of the
remaining quantity. Engine SHALL publish the fraction only; it SHALL
NOT compute quantities, lots, fills or the remaining exposure.

#### Scenario: Two quarter legs

- **WHEN** two partial takes each have `fraction_of_initial` 0.25 and
  the initial quantity is 100
- **THEN** each SHALL represent a reduction of 25
- **AND** after both the remaining exposure SHALL be 50.

### Requirement: Final take closes all remaining

The existing take-profit of the profile SHALL be the final take of the
ladder. It SHALL close all remaining exposure at the moment its level
is reached. Its configuration, aggregation and outputs SHALL be
unchanged by the presence of partial takes.

#### Scenario: Final after two legs

- **WHEN** two 25% partial takes were reached before the final take
- **THEN** the final take SHALL close the remaining 50% of the initial
  quantity.

### Requirement: Price-ordered traversal of take levels

The relative order of partial take levels and the final take level
SHALL NOT affect spec validity. A consumer executing the ladder SHALL
traverse touched take levels in price order away from entry:

- a partial take reduces the position and the traversal continues;
- the final take closes all remaining exposure and stops the
  traversal;
- at an equal level, a partial take precedes the final take.

Partial takes beyond the final take SHALL never execute once the final
take is reached.

#### Scenario: Partial beyond final

- **WHEN** a long entry at 100 has partial takes at 102, 106 and 108
  of 25% each and a final take at 104
- **AND** one bar reaches a high of 110 without touching any stop
- **THEN** the consumer SHALL fill 25% at 102 and close the remaining
  75% at 104
- **AND** SHALL NOT fill the partial takes at 106 and 108.

#### Scenario: Partial beyond final is a valid spec

- **WHEN** a spec has a final take at +8% and a partial take at +10%
- **THEN** the spec SHALL validate.

#### Scenario: Stop wins over takes

- **WHEN** a bar touches the stop
- **THEN** the stop SHALL close all remaining exposure
- **AND** no take level SHALL be traversed on that bar.

### Requirement: Disabling the initial take affects only the final take

A managed `disable_initial_tp` action SHALL disable only the final
take. Partial takes SHALL remain in force.

#### Scenario: Final take disabled

- **WHEN** managed policy has applied `disable_initial_tp` to a trade
  with two 25% partial takes
- **THEN** both partial takes SHALL still execute when their levels are
  reached
- **AND** the remaining 50% SHALL stay open until another exit closes
  it.

### Requirement: Partial fills do not feed back into Engine

No Engine input, live or historical, SHALL carry the fact that a
partial take filled. The managed state machine, its phases and the
historical managed projection SHALL NOT depend on partial takes or on
the position quantity.

#### Scenario: Open-trade projection with a ladder

- **WHEN** an open-trade projection runs for a trade whose entry had
  partial takes
- **THEN** its request, receipt and result SHALL be identical in shape
  and value to the same trade without partial takes.

### Requirement: Partial take validation

Static validation SHALL reject a spec where:

- `fraction_of_initial` is not strictly between 0 and 1;
- for any profile, the fractions of the partial takes in force
  (`always_on` plus that profile) sum to 1 or more;
- a profile with partial takes in force has no `take_profit` rule in
  force;
- `pct` or `distance.multiplier` is not positive.

Validation SHALL NOT compare partial take levels with the final take.

#### Scenario: Fractions sum to one

- **WHEN** `always_on` has a partial take of 0.5 and the `aligned`
  profile adds a partial take of 0.5
- **THEN** validation SHALL fail for the `aligned` profile.

#### Scenario: Partial takes without a final take

- **WHEN** a profile has partial takes in force and no `take_profit`
  rule in `always_on` or that profile
- **THEN** validation SHALL fail.

#### Scenario: Invalid fraction

- **WHEN** a partial take has `fraction_of_initial` 0, 1 or 1.2
- **THEN** validation SHALL fail.

#### Scenario: Validation without market data

- **WHEN** a spec violates any partial take rule
- **THEN** the canonical strategy validator SHALL reject it without
  loading market data.

### Requirement: Stable take identity

The `instance_id` of a partial take rule SHALL be its canonical
`take_id`. It SHALL be unique across the whole exit policy, by the
existing exit-rule uniqueness rule, and SHALL appear unchanged as the
`take_id` and attribution `rule_id` on every contract that carries the
leg.

#### Scenario: Take identity on the wire

- **WHEN** a partial take with `instance_id` `pt_1pct` is projected
  onto an entry
- **THEN** its `take_id` and attribution `rule_id` SHALL both be
  `pt_1pct`.
