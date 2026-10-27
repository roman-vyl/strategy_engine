## ADDED Requirements

### Requirement: Signal-close desired entry
For a spec with `components.trigger.entry_price: "signal_close"`, live-entry SHALL return a non-null `desired_entry` for a
target bar only when that bar is a signal bar of one side (that side's entry is allowed on the target bar), with
`planned_entry_price` equal to the target bar close and `source_plan_bar_open_time_ms` equal to the target bar. The
response shape SHALL be the same as for `anchor` plans.

#### Scenario: Signal bar
- **WHEN** the target bar is a long signal bar with close 100.5, stop distance 1.2 and take distance 6
- **THEN** `desired_entry` SHALL have `planned_entry_price` `"100.5"`, `initial_stop_price` `"99.3"` and
  `initial_take_price` `"106.5"`
- **AND** SHALL contain no field that an `anchor` plan does not contain

#### Scenario: Bar after the signal
- **WHEN** the target bar follows a signal bar and is not itself a signal bar
- **THEN** `desired_entry` SHALL be `null`

#### Scenario: Anchor plan unchanged
- **WHEN** a spec has no `entry_price`
- **THEN** the live-entry response SHALL be byte-identical to the response before this change
