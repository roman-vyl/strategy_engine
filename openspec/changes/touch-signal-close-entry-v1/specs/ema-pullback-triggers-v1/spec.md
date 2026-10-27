## ADDED Requirements

### Requirement: Touch trigger entry price mode
`components.trigger` with `component_id: "touch_anchor"` SHALL accept an optional `entry_price` of `"anchor"` or
`"signal_close"`, defaulting to `"anchor"`. Engine SHALL reject any other value, and SHALL reject `entry_price` on any
other trigger component. The trigger mask (`touch`, `close_ok`, `trigger`) SHALL NOT depend on `entry_price`.

#### Scenario: Default mode
- **WHEN** a touch_anchor spec has no `entry_price`
- **THEN** every PotentialEntry, live-entry response and node identity SHALL be byte-identical to the result before this
  change

#### Scenario: Invalid mode
- **WHEN** `entry_price` is `"ema"`, or `entry_price` is set with `component_id: "reclaim_anchor"`
- **THEN** Engine SHALL fail with a typed invalid-request error before evaluation

### Requirement: Signal-close potential entries
In `signal_close` mode the side's PotentialEntry SHALL be present on bar `i` only when that side's `entry_allowed[i]`
is true. Its entry SHALL be `close[i]`; stop and take SHALL be `close[i] ∓ stop_distance[i]` and
`close[i] ± take_distance[i]` (short mirrored) from the exit policy on bar `i`. On every other bar the side SHALL have no
entry, stop or take.

#### Scenario: Touch bar with allowed setup
- **WHEN** on bar `i` the long setup is allowed, `low[i] <= anchor[i]` and `close[i] >= anchor[i]`
- **THEN** the long PotentialEntry on bar `i` SHALL have entry `close[i]` and stop `close[i] - stop_distance[i]`

#### Scenario: Armed bar without touch
- **WHEN** on bar `i` the long setup is allowed and `close[i] >= anchor[i]` but `low[i] > anchor[i]`
- **THEN** the long PotentialEntry on bar `i` SHALL be absent (in `anchor` mode it is present at `anchor[i]`)

#### Scenario: Touch bar blocked by the vote
- **WHEN** bar `i` is a touch bar but the weighted vote blocks the side on bar `i`
- **THEN** the side's PotentialEntry on bar `i` SHALL be absent

#### Scenario: False break
- **WHEN** bar `i` touches and closes beyond the anchor and bar `i+1`, still inside the `active_bars` window, touches and
  closes on our side
- **THEN** bar `i` SHALL have no entry and bar `i+1` SHALL have entry `close[i+1]`
