## ADDED Requirements

### Requirement: Impulse ATR operand shape

An impulse ATR reference SHALL be `{"impulse_atr": {"episode", "atr"}}`; both are required and no other field is allowed. `episode`
SHALL name a declared episode and `atr` SHALL be a feature request of kind `atr` on the base timeframe. It SHALL be accepted where a
leg sum is accepted and rejected as the operand of a `change`.

#### Scenario: Malformed impulse ATR

- **WHEN** `atr` is missing, of another kind or on another timeframe, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Impulse ATR value

On a bar `t` with a valid wave of the current touch, the value SHALL be `|peak_price − origin_price| / atr[P]`. It SHALL be missing
when the touch has no valid wave, a price is not finite, or `atr[P]` is not finite or not above 0. Bars after `t` SHALL NOT be read.

#### Scenario: Twelve average candles

- **WHEN** the impulse height is 6 and the ATR on the peak bar is 0.5
- **THEN** the value SHALL be 12 on every bar of that touch.

#### Scenario: ATR not yet defined

- **WHEN** the peak bar lies before the first full ATR window
- **THEN** the value SHALL be missing.
