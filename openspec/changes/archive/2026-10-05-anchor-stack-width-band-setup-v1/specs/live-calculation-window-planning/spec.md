## ADDED Requirements

### Requirement: History policy for the anchor stack width band setup

The live history planner SHALL record an explicit
zero-additional-history entry for `anchor_stack_width_band_setup`,
at top level and as a `composite_setup` child. The warm-up of its EMA
and ATR features SHALL be counted by the existing per-feature policy.

#### Scenario: Band setup on a higher-timeframe ATR

- **WHEN** a spec declares `anchor_stack_width_band_setup` with
  `atr_timeframe` `1h`
- **THEN** the resolved requirements SHALL include a
  zero-additional-history entry for the setup
- **AND** the `1h` ATR warm-up SHALL be counted by the per-feature
  policy.
