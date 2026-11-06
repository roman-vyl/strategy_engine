# recursive-rsi-feature-v1 Specification

## Purpose
Provide a reproducible recursive RSI feature for composable strategy expressions without changing the existing rolling-mean RSI contract.
## Requirements
### Requirement: Recursive gain and loss calculation

The Engine SHALL expose `rsi_ewm` on close with a strict positive integer period N. At the first input candle it SHALL seed gain and loss averages to zero and set delta to zero. At subsequent candles it SHALL recursively update both averages with alpha=1/N, without adjusted weights or a simple-mean seed. RSI SHALL equal 100*gain_average/(gain_average+loss_average). A zero denominator SHALL return missing; one-sided positive averages SHALL yield 100 or 0 respectively. A nonfinite close SHALL invalidate this and subsequent recursive values within that calculation prefix rather than silently skip or reset it.

#### Scenario: Same-prefix reference parity
- **WHEN** a finite close prefix is evaluated with period168
- **THEN** every finite value SHALL match zero-first-delta gain/loss EWM with adjust=false and alpha=1/168 within absolute tolerance1e-9
- **AND** missing masks SHALL match, including a flat prefix.

#### Scenario: Invalid candle
- **WHEN** a nonfinite close occurs in the prefix
- **THEN** this and subsequent feature values SHALL be missing for that calculation.

### Requirement: Validation and compatibility

The feature SHALL accept only close, a positive nonboolean integer period and no dependencies or extra parameters. Catalog and schema SHALL advertise it distinctly from `rsi`. Existing rsi values, request validation and identities SHALL remain unchanged.

#### Scenario: Unsupported parameter
- **WHEN** rsi_ewm includes a boolean period, nonpositive period or unknown parameter
- **THEN** validation SHALL reject it before data calculation.

#### Scenario: Legacy RSI request
- **WHEN** an existing rsi manifest is evaluated unchanged
- **THEN** its rolling-mean values and identity SHALL remain unchanged.

### Requirement: History and visibility

Calculation SHALL use the supplied historical prefix before output-period slicing. The prefix origin SHALL be identifiable from execution metadata. Exact reference parity SHALL be claimed only for matching prefixes or proven equivalent state. Earlier values SHALL not change when only future candles are appended. HTF values SHALL be visible only after their source bucket closes.

#### Scenario: Append future candles
- **WHEN** future bars are appended with the same prefix origin
- **THEN** previously available feature values SHALL remain unchanged.

#### Scenario: Different history origin
- **WHEN** two runs use different seed origins
- **THEN** their origins SHALL be identifiable and exact seed parity SHALL NOT be asserted solely from using the same period.

