## Why

Research metric **W1r "open interest on the pullback against open interest in the impulse"** of vote W8 for EMA200:
`W1r = kR / kI`, with `kI = O1 / rI` (OpenSpec `ki-abs-operand-v1`) and `kR = O2 / rR`. kR is a pure composition of existing
operands: `ratio(leg_change {pullback, open_interest}, abs(leg_change {pullback, close}))`. Its parity is exact
(`engine-tasks/ema200/parity_kr/`).

W1r is defined only where `kI > 0.05`, i.e. where open interest grew in the impulse. The owner confirmed on 2026-10-26 at 20:00
that this condition is meaning, not a guard: with a negative denominator the sign flips and the reading breaks. Without it the
vote is worse (BTC 10.0 vs 11.7k, SOL 7.9 vs 8.4k).

The only obstacle is the rule "a side of a ratio SHALL NOT be a ratio". It was set when no metric needed it. Owner 20:29 «давай».

## What Changes

- **A side of a ratio may be a ratio.** Every other rule of the ratio stays as is: the value is `left / right`, it is missing when
  a side is missing or non-finite, and the bound is `right > right_floor`.
- **W1r** is `ratio(kR, kI, right_floor 0.05)` in the config, where the 0.05 is the owner's `kI > 0.05`. The Engine holds no number.
- No new operand and no new node family.

Not in this change: W1d (difference operand), W2d, W8, the voting module, deploy.
