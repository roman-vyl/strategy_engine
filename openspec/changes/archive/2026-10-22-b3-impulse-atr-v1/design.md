## Context

- Research reference: `altvals.py`: `A48 = atr(H, L, C)` (rolling mean of the true range over 48 bars, the Engine kind `atr`
  period 48); `b3h = Hs / A48[P]`, `Hs = |Pp − Sp|`, for every eligible entry (no `Hs > 0` condition).
- `origin_price`, `peak_price` are the touch-table prices used by A1, A3, C3.1 and C5.

## Decisions

### D1. Operand `impulse_atr`

`{"impulse_atr": {"episode", "atr": {"kind": "atr", "params": {"period": N}}}}`, both required. `atr` SHALL be of kind `atr` on the
base timeframe; its period is config. The value reads `atr` at the peak bar `P ≤ t` only, so it does not change within a touch.

Rejected: `ratio(height, feature atr)`. A feature operand is read at `t`, not at `P`; reading at `P` needs the episode, so the
division belongs to one operand, as `candle` already normalises by its own ATR.

### D2. Missing cases

Missing where the touch has no valid wave, a price is not finite, or `atr[P]` is not finite or `≤ 0` (start of history). A zero
height is a value of 0, as in research.

### D3. Identity

Own node family `predicate.impulse_atr`, no params, upstream the episode and the ATR column node (as `candle` does), so candidates
with the same ATR share both.
