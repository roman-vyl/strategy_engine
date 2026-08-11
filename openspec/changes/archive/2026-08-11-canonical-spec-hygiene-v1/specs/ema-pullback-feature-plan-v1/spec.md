## RENAMED Requirements

- FROM: `### Requirement: Exact feature discovery parity`
- TO: `### Requirement: Deterministic feature discovery`

## MODIFIED Requirements

### Requirement: Deterministic feature discovery

Each planned feature's `output_id` SHALL follow its kind's fixed template: `ema_close_{timeframe}_{period}` for EMA, `atr_close_{timeframe}_{period}` for ATR, `rsi_close_{timeframe}_{period}` for RSI, and `{kind}_close_{timeframe}_{period}` for each of `adx`, `di_plus`, `di_minus`. A derived ATR-distance feature's `output_id` SHALL equal its base ATR `output_id` suffixed with `_x` and the multiplier encoded as `str(float(multiplier))` with `.` replaced by `_`, and SHALL declare exactly one dependency referencing that base ATR `output_id`. When more than one part of a strategy spec references the same `output_id`, the planner SHALL include exactly one feature for it. The anchor-stack fast, anchor, and slow features SHALL be the first three entries in the resulting plan. The planner SHALL expose stable lookup mappings, keyed by role, instance ID, or timeframe/period, that resolve to these same `output_id`s for anchor stack, contexts, setups, exits, RSI, EMA, and ADX/DMI features.

#### Scenario: Build the complete feature matrix

- **WHEN** a strategy spec references features across anchor stack, contexts, setups, exits, RSI, EMA, and ADX/DMI
- **THEN** each feature's `output_id` SHALL match its kind-specific template
- **AND** the anchor-stack features SHALL be the first three entries in the plan
- **AND** a feature referenced from more than one section SHALL appear exactly once
- **AND** every lookup mapping SHALL resolve to the matching planned feature's `output_id`.
