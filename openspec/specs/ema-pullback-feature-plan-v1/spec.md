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
