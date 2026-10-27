## ADDED Requirements

### Requirement: Engine-wide live-entry mode
Strategy Engine SHALL read `STRATEGY_ENGINE_LIVE_ENTRY_MODE` once at start, with allowed values `ema_anchor` (default when
unset) and `touch_trigger`, and SHALL refuse to start for any other value. The mode SHALL affect only the live-entry
endpoint; `/range`, `/range-batch`, `/managed-replay` and open-trade results SHALL be identical in both modes.

#### Scenario: Unset variable
- **WHEN** the variable is not set
- **THEN** every live-entry response SHALL be byte-identical to the response before this change

#### Scenario: Invalid value
- **WHEN** the variable is `close`
- **THEN** the service SHALL fail at start with an error naming the allowed values

#### Scenario: Range unaffected
- **WHEN** the same `/range` request is evaluated with the mode `ema_anchor` and with `touch_trigger`
- **THEN** both responses SHALL be byte-identical

### Requirement: Touch-trigger desired entry
In `touch_trigger` mode, for a `touch_anchor` strategy, live-entry SHALL return a non-null `desired_entry` only when the
target bar is a signal bar of one side (that side's final entry mask is true on the target bar). Its
`planned_entry_price` SHALL equal the target bar close, stop and take SHALL be that close minus/plus the exit-policy
distances of the target bar (short mirrored), `source_plan_bar_open_time_ms` SHALL equal the target bar, and the response
shape SHALL be the same as in `ema_anchor` mode. For any other target bar, and for a strategy with another trigger,
`desired_entry` SHALL be `null`.

#### Scenario: Signal bar
- **WHEN** the target bar is a long signal bar with close 100.5, stop distance 1.2 and take distance 6
- **THEN** `desired_entry` SHALL have `planned_entry_price` `"100.5"`, `initial_stop_price` `"99.3"` and
  `initial_take_price` `"106.5"`
- **AND** SHALL contain no field that an `ema_anchor` plan does not contain

#### Scenario: Armed bar without touch
- **WHEN** the long setup is allowed and the close is above the anchor but the low stayed above the anchor
- **THEN** `desired_entry` SHALL be `null` (in `ema_anchor` mode it is a plan at the anchor)

#### Scenario: Touch blocked by the vote
- **WHEN** the target bar touches and closes on our side but the weighted vote blocks the side on that bar
- **THEN** `desired_entry` SHALL be `null`

#### Scenario: False break then return
- **WHEN** bar `i` touches and closes beyond the anchor and bar `i+1`, inside the setup window, touches and closes on our
  side
- **THEN** target `i` SHALL return `null` and target `i+1` SHALL return a plan at `close[i+1]`

#### Scenario: Bar after the signal
- **WHEN** the target bar follows a signal bar and is not itself a signal bar
- **THEN** `desired_entry` SHALL be `null`
