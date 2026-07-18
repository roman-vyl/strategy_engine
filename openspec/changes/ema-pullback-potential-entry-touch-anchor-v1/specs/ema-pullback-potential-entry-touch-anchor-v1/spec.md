# Specification: EMA Pullback potential entry for touch-anchor v1

## ADDED Requirements

### Requirement: Additive potential-entry projection

The Strategy Engine SHALL provide an additive bar-aligned `PotentialEntry` projection for EMA Pullback without changing the existing feature, component, trigger, final-entry, exit-policy, or managed-replay semantics.

The projection SHALL be calculated from the same already evaluated range request and SHALL NOT cause a second indicator or strategy evaluation.

#### Scenario: Existing range calculation is reused

- **WHEN** an EMA Pullback range request is evaluated with potential-entry projection enabled
- **THEN** the engine SHALL execute the existing feature and strategy calculation once
- **AND** SHALL build `potential_entries` from the already calculated internal results
- **AND** SHALL preserve all existing range outputs except for the additive field.

### Requirement: Minimal PotentialEntry model

For each supported enabled side, `PotentialEntry` SHALL contain only `side`, `entry_price`, `stop_price`, and `take_price` vectors.

The engine SHALL NOT add a separate public `allowed`, `armed`, or `global_entry_allowed` field to this model. It SHALL NOT add order type, trigger type, labels, plan IDs, or duplicated spec/market hashes.

At every bar, entry, stop, and take SHALL either all be present or all be absent.

#### Scenario: Complete triple is published

- **WHEN** a supported enabled side has a valid potential entry on a bar
- **THEN** `entry_price`, `stop_price`, and `take_price` SHALL all contain non-null values at that bar.

#### Scenario: Partial triple is forbidden

- **WHEN** any required potential-entry value is unavailable or invalid on a bar
- **THEN** `entry_price`, `stop_price`, and `take_price` SHALL all be `null` at that bar.

### Requirement: Existing pre-trigger gate

The touch-anchor projector SHALL use the existing `SideSetupEvaluation.pre_trigger_allowed` vector as its internal strategy gate. It SHALL also reuse the already evaluated touch-anchor `close_ok` side precondition.

For long, `close_ok` SHALL require close to be greater than or equal to anchor. For short, `close_ok` SHALL require close to be less than or equal to anchor. The projector SHALL NOT recalculate these comparisons or re-parse the trigger configuration.

The engine SHALL NOT change the calculation of `pre_trigger_allowed` or the existing touch-anchor trace and SHALL NOT publish either value as a new top-level lifecycle state as part of this change.

#### Scenario: Pre-trigger denial suppresses the triple

- **WHEN** `pre_trigger_allowed` is false for a supported enabled side on a bar
- **THEN** all three potential prices for that side and bar SHALL be `null`.

#### Scenario: Wrong-side close suppresses a marketable plan

- **WHEN** `touch_anchor` is configured for long and close is below anchor on a bar
- **THEN** all three potential prices for long on that bar SHALL be `null`.
- **WHEN** `touch_anchor` is configured for short and close is above anchor on a bar
- **THEN** all three potential prices for short on that bar SHALL be `null`.

### Requirement: Touch-anchor price semantics

Version 1 SHALL produce potential-entry records only for a configured `touch_anchor` trigger.

When the pre-trigger gate, the touch-anchor `close_ok` precondition, and required values are ready, the potential entry price SHALL equal the current anchor EMA.

For long, stop SHALL equal anchor minus selected raw initial stop distance and take SHALL equal anchor plus selected raw initial take distance.

For short, stop SHALL equal anchor plus selected raw initial stop distance and take SHALL equal anchor minus selected raw initial take distance.

#### Scenario: Long touch-anchor prices

- **WHEN** `touch_anchor` is configured for an enabled long side and all required values are valid
- **THEN** `entry_price` SHALL equal the anchor EMA
- **AND** `stop_price` SHALL equal anchor minus selected raw initial stop distance
- **AND** `take_price` SHALL equal anchor plus selected raw initial take distance.

#### Scenario: Short touch-anchor prices

- **WHEN** `touch_anchor` is configured for an enabled short side and all required values are valid
- **THEN** `entry_price` SHALL equal the anchor EMA
- **AND** `stop_price` SHALL equal anchor plus selected raw initial stop distance
- **AND** `take_price` SHALL equal anchor minus selected raw initial take distance.

#### Scenario: Trigger firing does not suppress potential entry

- **WHEN** `touch_anchor` fires on a bar
- **AND** `pre_trigger_allowed` is true on that bar
- **AND** touch-anchor `close_ok` is true on that bar
- **AND** all required prices and distances are valid
- **THEN** the final entry mask MAY be true on that bar
- **AND** the complete potential-entry triple SHALL remain present on that same bar.

### Requirement: Reuse selected raw exit distances

Exit-policy evaluation SHALL preserve the selected raw absolute stop-loss and take-profit distance vectors required by the potential-entry projector.

Raw distance selection SHALL use the same always-on/profile composition, side-relative profile selection, and minimum-distance rules as existing exit-policy ratio selection.

The projector SHALL NOT recalculate ATR, read ATR multipliers independently, or derive potential stop/take prices by applying a close-relative ratio directly to the anchor.

Existing serialized stop/take ratios, readiness, profiles, evidence, and rule behavior SHALL remain unchanged.

#### Scenario: Raw ATR distance is applied to anchor

- **WHEN** close differs from anchor and an ATR-based initial stop or take rule is selected
- **THEN** the potential stop/take price SHALL use the selected raw absolute distance
- **AND** SHALL NOT use `anchor × close-relative ratio`.

#### Scenario: Existing exit-policy wire contract is preserved

- **WHEN** potential-entry support is added
- **THEN** the existing serialized stop/take ratios, readiness, profiles, and evidence SHALL remain semantically unchanged.

### Requirement: Positive and finite source values

A potential price triple SHALL be present only when `pre_trigger_allowed` and touch-anchor `close_ok` are true and the anchor, selected stop distance, selected take distance, and all derived prices are finite.

The anchor, selected stop distance, selected take distance, and all derived prices SHALL also be strictly greater than zero.

If any required value is unavailable, non-finite, zero, negative, or in warmup, all three potential prices for that side and bar SHALL be absent.

The engine SHALL NOT publish partial potential-entry triples or fallback values.

#### Scenario: Non-positive anchor suppresses the triple

- **WHEN** the anchor is zero or negative on a bar
- **THEN** all three potential prices for that side and bar SHALL be `null`.

#### Scenario: Non-positive stop distance suppresses the triple

- **WHEN** the selected raw initial stop distance is zero or negative on a bar
- **THEN** all three potential prices for that side and bar SHALL be `null`.

#### Scenario: Non-positive take distance suppresses the triple

- **WHEN** the selected raw initial take distance is zero or negative on a bar
- **THEN** all three potential prices for that side and bar SHALL be `null`.

#### Scenario: Non-positive derived price suppresses the triple

- **WHEN** any derived entry, stop, or take price is zero or negative on a bar
- **THEN** all three potential prices for that side and bar SHALL be `null`.

### Requirement: Stable potential_entries response shape

Every successful EMA Pullback strategy range result SHALL include a top-level additive `potential_entries` object.

For a configured non-`touch_anchor` trigger, `potential_entries` SHALL be an empty object.

For a configured `touch_anchor` trigger, `potential_entries` SHALL contain only keys for enabled sides. A disabled side SHALL be omitted rather than represented by all-null vectors.

For every included enabled side, potential numeric values SHALL serialize as normalized decimal text or JSON `null`, aligned to the same bar axis as existing entries and exit-policy vectors.

The parent strategy result SHALL remain the source of strategy identity, config identity, market identity, range identity, and market-data provenance.

#### Scenario: Unsupported trigger returns empty object

- **WHEN** a successful range evaluation uses a trigger other than `touch_anchor`
- **THEN** the response SHALL contain `"potential_entries": {}`.

#### Scenario: Touch-anchor includes enabled sides only

- **WHEN** a successful range evaluation uses `touch_anchor`
- **AND** only the long side is enabled
- **THEN** `potential_entries` SHALL contain the `long` key
- **AND** SHALL omit the `short` key.

#### Scenario: Enabled side remains present through warmup

- **WHEN** a successful range evaluation uses `touch_anchor` for an enabled side
- **AND** required values are unavailable on some bars
- **THEN** that side object SHALL remain present
- **AND** its vectors SHALL contain aligned `null` values on those bars.

### Requirement: Existing semantics remain unchanged

This change SHALL NOT alter final entry masks, trigger masks or traces, current exit-policy wire output, managed replay, execution simulation, fills, order types, Runtime lifecycle, or Abi behavior.

#### Scenario: Existing strategy outputs retain their semantics

- **WHEN** the same range request is evaluated before and after this additive capability
- **THEN** all pre-existing strategy outputs SHALL retain their prior semantics
- **AND** only the additive `potential_entries` field MAY differ by being newly present.
