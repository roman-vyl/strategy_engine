## ADDED Requirements

### Requirement: Wave measure, leg volume and forming candle identity

`wave_measure`, `leg_volume` and `forming_candle` operands SHALL each have their own node family whose identity carries their
params and the identities of their upstream episode and ATR feature. Labels SHALL NOT enter the identity.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level of a vote input or a bound of a range over one of these operands
- **THEN** each operand SHALL be computed once per batch per side.

### Requirement: Wave measure, leg volume and forming candle cost

`wave_measure`, `leg_volume` with `sum` and `forming_candle` SHALL cost O(n) per series. `leg_volume` with `top_mean` SHALL be
computed once per touch for the impulse and only on bars with a valid wave for the pullback. A spec without these operands SHALL
have the same node set and the same results as before this change.

#### Scenario: No compute regression

- **WHEN** a spec has none of these operands
- **THEN** no node of these families SHALL be created.
