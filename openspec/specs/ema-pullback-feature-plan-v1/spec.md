# EMA Pullback Feature Plan v1 Specification

## Purpose

Define Strategy Engine-owned feature planning, canonical BBB compatibility, exact feature discovery, honest capability metadata, and production dependency boundaries for EMA Pullback.
## Requirements
### Requirement: Caller supplies strategy semantics, not indicator plans

The public strategy boundary SHALL accept a strategy envelope. Feature discovery SHALL occur inside Strategy Engine. A BBB caller SHALL NOT need to construct or submit an IndicatorPlan for strategy evaluation.

#### Scenario: Request strategy-owned feature planning

- **WHEN** a caller submits a canonical EMA Pullback strategy envelope
- **THEN** Strategy Engine SHALL discover the required indicator features internally
- **AND** the caller SHALL NOT need to supply an `IndicatorPlan`.

### Requirement: Canonical BBB spec compatibility

Version 1 SHALL accept the canonical JSON shape produced by BBB `strategy_spec_to_dict`. Unsupported or malformed structures SHALL fail with a structured 4xx response and SHALL NOT silently omit requested features.

#### Scenario: Submit a malformed canonical strategy spec

- **WHEN** a canonical EMA Pullback structure is unsupported or malformed
- **THEN** the request SHALL fail with a structured 4xx response
- **AND** requested features SHALL NOT be silently omitted.

### Requirement: Honest capability advertisement

The strategy catalog SHALL advertise `supports_feature_planning=true`. Range-evaluation flags and the evaluation stage SHALL match the semantics currently wired into the production evaluator, and capabilities beyond that advertised stage SHALL NOT report fabricated success.

#### Scenario: Inspect strategy capability metadata

- **WHEN** a caller inspects the EMA Pullback strategy catalog entry
- **THEN** feature planning SHALL be advertised as supported
- **AND** range-evaluation flags and stage SHALL accurately describe the production evaluator.

### Requirement: No legacy production imports

Production code SHALL NOT import from `legacy_source` or BBB packages.

#### Scenario: Enforce the production dependency boundary

- **WHEN** architecture checks inspect production imports
- **THEN** no production module SHALL import `legacy_source` or BBB packages.

### Requirement: Deterministic feature discovery

Each planned feature's `output_id` SHALL follow its kind's fixed template: `ema_close_{timeframe}_{period}` for EMA, `atr_close_{timeframe}_{period}` for ATR, `rsi_close_{timeframe}_{period}` for RSI, and `{kind}_close_{timeframe}_{period}` for each of `adx`, `di_plus`, `di_minus`. A derived ATR-distance feature's `output_id` SHALL equal its base ATR `output_id` suffixed with `_x` and the multiplier encoded as `str(float(multiplier))` with `.` replaced by `_`, and SHALL declare exactly one dependency referencing that base ATR `output_id`. When more than one part of a strategy spec references the same `output_id`, the planner SHALL include exactly one feature for it. The anchor-stack fast, anchor, and slow features SHALL be the first three entries in the resulting plan. The planner SHALL expose stable lookup mappings, keyed by role, instance ID, or timeframe/period, that resolve to these same `output_id`s for anchor stack, contexts, setups, exits, RSI, EMA, and ADX/DMI features.

#### Scenario: Build the complete feature matrix

- **WHEN** a strategy spec references features across anchor stack, contexts, setups, exits, RSI, EMA, and ADX/DMI
- **THEN** each feature's `output_id` SHALL match its kind-specific template
- **AND** the anchor-stack features SHALL be the first three entries in the plan
- **AND** a feature referenced from more than one section SHALL appear exactly once
- **AND** every lookup mapping SHALL resolve to the matching planned feature's `output_id`.

### Requirement: Predicate feature references use the canonical plan

Feature references inside `composite_setup` children SHALL be planned
as ordinary `PlannedFeature` entries of the strategy's single
`IndicatorPlan`:

- they SHALL be normalized, validated and labelled by the canonical
  feature-kind contract, which also produces the labels of every other
  planned feature, and deduplicated by the same `add()`;
- semantic setup children SHALL be planned by their existing
  per-component planning under the internal key
  `"{instance_id}/{child_id}"`.

For a spec without `composite_setup`, the plan (features, order and
`plan_hash`) SHALL be unchanged.

#### Scenario: Shared feature

- **WHEN** a predicate requests `adx` on `1h` with period 14
- **AND** a `trend_strength_episode_blocker` requests the same ADX
- **THEN** the plan SHALL contain one `adx` feature for (`1h`, 14).

#### Scenario: Plan unchanged without composite

- **WHEN** a spec contains no `composite_setup`
- **THEN** its `plan_hash` SHALL equal the `plan_hash` produced before
  this change.

### Requirement: Label collisions fail closed

If the identity of a predicate feature reference differs from the
identity of the planned feature already stored under the same label,
planning SHALL fail with `InvalidRequestError`. The predicate SHALL NOT
read a series other than the one it requested.

#### Scenario: EMA source collision

- **WHEN** the anchor stack plans `ema` on `1h`, period 100, source
  `close`
- **AND** a predicate requests `ema` on `1h`, period 100, source `open`
- **THEN** planning SHALL fail with `InvalidRequestError`.

### Requirement: Timeframe support

A predicate feature reference SHALL accept any timeframe that the
indicator evaluator accepts: `base` or an integral multiple of the base
timeframe. Any other timeframe SHALL fail at the same point, and with
the same error, as for any other planned feature.

#### Scenario: Mixed timeframes in one composite

- **WHEN** one composite references features on `5m`, `15m`, `1h` and
  `4h` with a `5m` base
- **THEN** all four SHALL be planned in the one plan
- **AND** SHALL be evaluated through the existing completed-bar
  alignment.

### Requirement: Composite phase condition features use the canonical plan

Planning SHALL recurse into `composite_phase_condition` children:

- feature references of predicate children SHALL be planned as ordinary
  `PlannedFeature` entries, through the same canonical feature-kind
  contract, the same `add()` and the same fail-closed label-collision
  check as `composite_setup` predicate features;
- atom children SHALL be planned by the existing atom planning: ATR for
  `mfe_atr`, ADX/DMI for `adx_di_threshold`.

For a spec without `composite_phase_condition`, the plan (features,
order and `plan_hash`) SHALL be unchanged.

#### Scenario: Shared ADX column

- **WHEN** a composite phase condition predicate requests `adx` on `1h`
  with period 14
- **AND** a `composite_setup` predicate requests the same feature
- **THEN** the plan SHALL contain one `adx` feature for (`1h`, 14).

#### Scenario: Plan unchanged without composite phase condition

- **WHEN** a managed spec has only atomic phase conditions
- **THEN** its `plan_hash` SHALL equal the `plan_hash` produced before
  this change.

### Requirement: Partial take distances use the canonical plan

An `atr_partial_take` rule SHALL plan its ATR distance exactly like an
`atr_take_profit` rule with the same `distance`: through the same
canonical exit-distance planning, ATR feature sharing by label and
fail-closed label-collision check. A `pct_partial_take` rule SHALL plan
no features.

For a spec without partial take rules, the plan (features, order and
`plan_hash`) SHALL be unchanged.

#### Scenario: Shared ATR column

- **WHEN** an `atr_partial_take` and an `atr_stop_loss` both use base
  timeframe and period 14
- **THEN** the plan SHALL contain one ATR feature for (base, 14).

#### Scenario: Pct partial take plans nothing

- **WHEN** the only change to a spec is an added `pct_partial_take`
- **THEN** its planned features SHALL equal those of the spec without
  that rule.

#### Scenario: Plan unchanged without partial takes

- **WHEN** a spec has no partial take rules
- **THEN** its `plan_hash` SHALL equal the `plan_hash` produced before
  this change.

