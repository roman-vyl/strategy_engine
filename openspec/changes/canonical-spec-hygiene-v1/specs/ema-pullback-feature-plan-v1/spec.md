## RENAMED Requirements

- FROM: `### Requirement: Exact feature discovery parity`
- TO: `### Requirement: Deterministic feature discovery`

## MODIFIED Requirements

### Requirement: Deterministic feature discovery

Each planned feature's `output_id` SHALL be a deterministic function of its kind, timeframe, and period (and multiplier for a derived ATR-distance feature): identical inputs SHALL always resolve to the same `output_id`. When more than one part of a strategy spec references the same `output_id`, the planner SHALL include exactly one feature for it. The anchor-stack fast, anchor, and slow features SHALL be the first three entries in the resulting plan. A derived `atr_distance` feature SHALL declare exactly one dependency, referencing its base ATR feature's `output_id`. The planner SHALL expose stable lookup mappings, keyed by role, instance ID, or timeframe/period, that resolve to these same `output_id`s for anchor stack, contexts, setups, exits, RSI, EMA, and ADX/DMI features.

#### Scenario: Build the complete feature matrix

- **WHEN** a strategy spec references features across anchor stack, contexts, setups, exits, RSI, EMA, and ADX/DMI
- **THEN** the anchor-stack features SHALL be the first three entries in the plan
- **AND** a feature referenced from more than one section SHALL appear exactly once
- **AND** every lookup mapping SHALL resolve to the matching planned feature's `output_id`.
