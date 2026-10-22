## ADDED Requirements

### Requirement: Wave measure operand shape

A wave measure reference SHALL be `{"wave_measure": {"episode", "measure", "touch"?, "atr"?}}`. `episode` SHALL name a declared
episode. `measure` SHALL be `impulse_atr`, `speed_ratio`, `duration_ratio`, `efficiency_gap` or `depth_share`. `touch` SHALL be
`current` (default) or `previous`, and `previous` SHALL be accepted only with `depth_share`. `atr` SHALL be required by
`impulse_atr` and rejected with every other measure.

#### Scenario: Malformed wave measure

- **WHEN** a wave measure has an unknown measure or field, `touch: previous` with `speed_ratio`, or `impulse_atr` without `atr`
- **THEN** static validation SHALL reject the spec.

### Requirement: Wave measure use

A wave measure, a leg volume and a forming candle reference SHALL each be accepted as a side of a `ratio`, as the operand of a
`range`, as an operand of a `compare` and as the operand of a weighted vote input, and SHALL be rejected as the operand of a
`change`.

#### Scenario: Change operand

- **WHEN** a `change` predicate has a wave measure, leg volume or forming candle operand
- **THEN** static validation SHALL reject the spec.

### Requirement: Wave measure points

On bar `t`, with `S*`, `P`, `origin_price` and `peak_price` of the current touch, `g` = +1 long and −1 short and
`H = |peak_price − origin_price|`, every wave measure SHALL be missing when the touch has no valid wave, when `H ≤ 0` or when an
input is not finite. Bars after `t` SHALL NOT be read.

#### Scenario: No wave

- **WHEN** the episode is not active on `t`
- **THEN** every wave measure SHALL be missing.

### Requirement: Impulse height in ATR

`impulse_atr` SHALL be `H ÷ ATR[P]`, where `atr` is a feature of kind `atr` or `atr_wilder` on the base timeframe and `ATR[P]` its
value on the peak bar. It SHALL be missing when `ATR[P]` is not greater than 0.

#### Scenario: Height

- **WHEN** `origin_price` is 100, `peak_price` 112 and `ATR[P]` is 2
- **THEN** the value SHALL be 6.

### Requirement: Pullback speed ratio

`speed_ratio` SHALL be `(|peak_price − close[t]| ÷ (t − P + 1)) ÷ (H ÷ (P − S* + 1))`. The pullback SHALL count the peak bar.

#### Scenario: Speed

- **WHEN** `S*` is 10, `P` is 19, `H` is 10, `t` is 23 and `|peak_price − close[t]|` is 5
- **THEN** the value SHALL be (5 ÷ 5) ÷ (10 ÷ 10) = 1.

### Requirement: Duration ratio

`duration_ratio` SHALL be `(t − P + 1) ÷ (P − S* + 1)`.

#### Scenario: Peak bar

- **WHEN** `S*` is 10, `P` is 19 and `t` is 19
- **THEN** the value SHALL be 0.1.

### Requirement: Efficiency gap

`efficiency_gap` SHALL be `ER(P, t) − ER(S*, P)` with `ER(a, z) = |close[z] − close[a]| ÷ Σ |close[u] − close[u−1]|` over
`u = a+1..z`. It SHALL be missing when `t = P` or when either sum is 0.

#### Scenario: Straight impulse, choppy pullback

- **WHEN** the impulse closes rise by 1 on every bar and the pullback closes go −1, +1, −1, −1
- **THEN** the value SHALL be 0.5 − 1 = −0.5.

### Requirement: Depth share

`depth_share` with `touch: current` SHALL be `g · (peak_price − X) ÷ H`, `X` the lowest low (long) or highest high (short) of bars
`P..t`, both inclusive.

#### Scenario: Depth

- **WHEN** the side is long, `origin_price` 100, `peak_price` 110 and the lowest low of bars `P..t` is 104
- **THEN** the value SHALL be 0.6.

### Requirement: Depth share of the previous wave

`depth_share` with `touch: previous` SHALL read the previous touch row of the same episode (peak `P0`, `peak_price0`,
`origin_price0`) and SHALL be `g · (peak_price0 − X0) ÷ |peak_price0 − origin_price0|`, `X0` the extreme of bars `P0..S*` of the
current touch, both inclusive. It SHALL be missing on the first touch of an episode, when `S* ≤ P0` or when the previous height is 0.

#### Scenario: First touch

- **WHEN** the current touch is the first of its episode
- **THEN** the previous depth share SHALL be missing.

### Requirement: Leg volume operand shape

A leg volume reference SHALL be `{"leg_volume": {"episode", "leg", "aggregate", "bars"?, "top_share"?}}`. `leg` SHALL be
`impulse` or `pullback`, `aggregate` `sum` or `top_mean`, `bars` `all` (default) or `own_color`. `top_share` SHALL be a number in
(0, 1], required with `top_mean` and rejected otherwise. `top_mean` with `own_color` SHALL be rejected.

#### Scenario: Malformed leg volume

- **WHEN** `top_mean` has no `top_share`, `top_share` is 0 or above 1, or `sum` carries `top_share`
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg volume value

The legs SHALL be those of the leg mean operand: impulse `[S*, P]`, pullback `[P+1, t]`. `sum` SHALL be the sum of the volumes
of the leg bars. `top_mean` SHALL be the mean of the `k` largest volumes, `k = max(1, ceil(top_share · L))` in float64, `L` the
number of leg bars. The value SHALL be missing when there is no valid wave, the leg is empty or an input of the leg is not finite.

#### Scenario: Top mean

- **WHEN** the pullback has 12 bars, `top_share` is 0.1 and its two largest volumes are 50 and 30
- **THEN** `k` SHALL be 2 and the value 40.

### Requirement: Own colour bars

With `bars: own_color` only the bars of the leg's own colour SHALL count: on the impulse `close > open` for a long and
`close < open` for a short, on the pullback the opposite. A bar with `close = open` SHALL never count.

#### Scenario: Short pullback

- **WHEN** the side is short and a pullback bar closes above its open
- **THEN** its volume SHALL count in the own-colour pullback sum.

### Requirement: Forming candle operand

A forming candle reference SHALL be `{"forming_candle": {"timeframe", "atr", "episode"?}}`, `timeframe` a multiple of the base
timeframe and `atr` an `atr_wilder` feature of the same timeframe. On bar `t` its value SHALL be `g · (close[t] − open) ÷ ATR`,
`open` the open of the first base bar of the epoch-aligned bucket containing `t` and `ATR` the value of the last closed candle
before that bucket.

#### Scenario: Daily body

- **WHEN** the side is long, the day opened at 100, `close[t]` is 97 and the previous day's ATR is 10
- **THEN** the value SHALL be −0.3.

### Requirement: Forming candle missing values

The forming candle value SHALL be missing when the ATR of the previous candle is missing or not greater than 0, or when `close[t]`
or `open` is not finite. With `episode` it SHALL also be missing where the current touch of that episode has no valid wave.
Bars after `t` SHALL NOT be read.

#### Scenario: No wave

- **WHEN** `episode` is set and the episode has no valid wave on `t`
- **THEN** the value SHALL be missing.
