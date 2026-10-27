## Context

- Research: `vol1h_bars` uses a cumulative sum with a leading 0, so `cs[i+1] − cs[i−11]` = `V[i−11..i]` and `cs[i−11] − cs[i−5771]` = `V[i−5771..i−12]`.
  It starts at `i ≥ 5771` and treats a missing volume as 0. Engine volume is never missing on a candle.
- The existing `rolling_max` / `rolling_min` kinds (`w8-rolling-extreme-v1`) live in `indicators/implementations/rolling_extreme.py` and
  share its validation and label pattern.

## Decisions

### D1. Kind `rolling_sum`

- Parameters: `period` (integer ≥ 1, required) and `lag` (integer ≥ 0, default 0). No other parameter.
- `source`: any bar field the Engine carries. The default is `volume`.
- Value on candle i is the sum of `x[i−lag−period+1 .. i−lag]`. It is missing until that window holds `period` finite values.
- On a higher timeframe the base bars see the last completed candle, as for any feature.
- The label carries source, period and lag.

### D2. Why `lag` lives in the feature

A ratio of "the last hour" over "the 20 days before it" needs the second window to end where the first begins. There is no generic shift
operand, and one parameter on the sum keeps it a single cached column.

Rejected: a separate `shift` operand. It would add a node family for one use.

### D3. Numerics

The research sums with a global cumulative sum, while pandas sums each rolling window. The two orders differ in the last bits. Parity is
reported at 1e-9 relative.

### D4. Parity reference

`vol1h_bars` on every bar of BTC, ETH and SOL (research perp 5m volume), compared bar by bar. Values on the EMA200 entries are reported
separately.
