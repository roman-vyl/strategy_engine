## ADDED Requirements

### Requirement: Entry order kind in the desired entry
A `DesiredEntry` projected from a `signal_close` plan SHALL contain `entry_order: "post_only_limit"`. A `DesiredEntry`
projected from an `anchor` plan SHALL NOT contain the `entry_order` key. `post_only_limit` SHALL mean: rest a limit order
at `planned_entry_price` that never takes liquidity, valid for the bar that opens right after
`source_plan_bar_open_time_ms`.

#### Scenario: Signal-close plan
- **WHEN** the target bar is a long signal bar of a `signal_close` spec with close 100.5
- **THEN** `desired_entry.planned_entry_price` SHALL be `"100.5"`
- **AND** `desired_entry.entry_order` SHALL be `"post_only_limit"`
- **AND** `source_plan_bar_open_time_ms` SHALL equal the target bar

#### Scenario: Bar after the signal
- **WHEN** the target bar follows a signal bar and is not itself a signal bar
- **THEN** `desired_entry` SHALL be `null`

#### Scenario: Anchor plan unchanged
- **WHEN** a spec without `entry_price` produces a plan
- **THEN** the response SHALL NOT contain `entry_order`
- **AND** SHALL be byte-identical to the response before this change
