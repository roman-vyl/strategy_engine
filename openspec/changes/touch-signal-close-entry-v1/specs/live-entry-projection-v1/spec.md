## ADDED Requirements

### Requirement: Engine-wide live-entry mode from the config file
Strategy Engine SHALL read `live_entry_mode` once at start from the TOML file named by `STRATEGY_ENGINE_CONFIG_PATH`, with
allowed values `ema_anchor` and `touch_trigger`, and `ema_anchor` when the path is unset, the file is absent or the key is
absent. It SHALL refuse to start on an unknown value, an unknown key or an unparsable file.

#### Scenario: No config file
- **WHEN** `STRATEGY_ENGINE_CONFIG_PATH` is unset or names a missing file
- **THEN** every live-entry response SHALL be byte-identical to the response before this change

#### Scenario: Invalid value
- **WHEN** the file contains `live_entry_mode = "close"`
- **THEN** the service SHALL fail at start with an error naming the allowed values

#### Scenario: Switch by restart
- **WHEN** the file is changed from `ema_anchor` to `touch_trigger` and the Engine is restarted
- **THEN** live-entry SHALL answer in `touch_trigger` mode

### Requirement: The mode affects only live-entry
`/range`, `/range-batch`, `/managed-replay` and open-trade results SHALL be identical in both modes.

#### Scenario: Range unaffected
- **WHEN** the same `/range` request is evaluated with the mode `ema_anchor` and with `touch_trigger`
- **THEN** both responses SHALL be byte-identical

### Requirement: Touch-trigger desired entry
In `touch_trigger` mode, for a `touch_anchor` strategy, live-entry SHALL return a plan only for a target bar on which one
side's final entry mask is true, priced at the target bar close with stop and take from that bar's exit-policy
distances, in the same response shape; otherwise `desired_entry` SHALL be `null`.

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
