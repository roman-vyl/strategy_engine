## MODIFIED Requirements

### Requirement: Define the desired entry contract

A non-null `DesiredEntry` SHALL contain:

```text
side
source_plan_bar_open_time_ms
planned_entry_price
initial_stop_price
initial_take_price
locked_exit_profile
```

`source_plan_bar_open_time_ms` SHALL equal the requested target bar.

Wire prices SHALL be positive normalized decimal text.

`locked_exit_profile` SHALL be one of `always_on`, `aligned`, `countertrend`, or `neutral`.

A `DesiredEntry` SHALL additionally contain `partial_takes` only when the
partial takes in force for its locked profile are not empty. Each element
SHALL be `{take_id, price, fraction_of_initial}`, with `price` positive
normalized decimal text frozen on the source-plan bar and
`fraction_of_initial` normalized decimal text. When there are none, the
key SHALL be absent. `initial_take_price` remains the final take, which
closes all remaining exposure.

#### Scenario: Long desired-entry price geometry

- **WHEN** a long `desired_entry` is returned
- **THEN** `initial_stop_price < planned_entry_price < initial_take_price` SHALL hold.

#### Scenario: Short desired-entry price geometry

- **WHEN** a short `desired_entry` is returned
- **THEN** `initial_take_price < planned_entry_price < initial_stop_price` SHALL hold.

#### Scenario: Desired entry without partial takes

- **WHEN** a spec has no partial take rules
- **THEN** the returned `desired_entry` SHALL NOT contain a `partial_takes` key
- **AND** SHALL be byte-identical to the response before partial takes were introduced.

#### Scenario: Partial take prices

- **WHEN** a long plan with `planned_entry_price` 100 has a `pct_partial_take` with `pct` 0.01 and an `atr_partial_take` with multiplier 2 and ATR 1.5 on the source-plan bar
- **THEN** their prices SHALL be 101 and 103
- **AND** for a short plan with the same inputs they SHALL be 99 and 97.

#### Scenario: Partial take geometry is not compared with the final take

- **WHEN** a long plan has `initial_take_price` 108 and a partial take at 110
- **THEN** the plan SHALL be returned with both
- **AND** every partial take price SHALL be above `planned_entry_price` for long and below it for short.

#### Scenario: Incomplete partial take

- **WHEN** any partial take in force for the side's locked profile has no valid positive profit-side price on the source-plan bar
- **THEN** the internal plan for that side SHALL be `null`
- **AND** Engine SHALL NOT return a `DesiredEntry` that omits that leg.
