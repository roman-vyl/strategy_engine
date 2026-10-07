## ADDED Requirements

### Requirement: History policy for the swing retrace feature

For a planned `swing_retrace` feature the live history planner SHALL
require, on the feature's own timeframe:

- `bars + 1` bars for `anchor: window`, as a finite-window requirement;
- for `anchor: ema_touch`, `bars + 1` bars plus the EMA convergence
  warm-up of the largest of `touch_period` and `stack_periods`, using
  the existing EMA convergence policy.

It SHALL NOT fail closed on this kind once the policy exists.

#### Scenario: Window anchor

- **WHEN** the plan contains `swing_retrace` on 5m with `anchor: window`
  and `bars` 96
- **THEN** the requirement SHALL be 97 bars of 5m.

#### Scenario: Touch anchor on a higher timeframe

- **WHEN** the plan contains `swing_retrace` on 4h with
  `anchor: ema_touch`, `bars` 180, `touch_period` 20 and
  `stack_periods` [20, 50, 100]
- **THEN** the requirement SHALL be 181 bars of 4h plus the EMA(100)
  convergence warm-up on 4h.

#### Scenario: Later window equals the full window

- **WHEN** the feature is evaluated on the planned window and on a
  longer window ending at the same bar
- **THEN** the values at that bar SHALL be equal.
