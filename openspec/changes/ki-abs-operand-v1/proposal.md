## Why

Research metric **kI "open interest per unit of impulse price move"** of vote W8 for EMA200: `kI = O1 / rI`, with
`O1 = 100 * (OI(P) / OI(S*) - 1)` and `rI = |100 * (C(P) / C(S*) - 1)|`. It is O1 normalised by the size of the impulse.
Agreed with the owner on 2026-10-26 (19:56, «да»). The rule for the OI value is `engine-tasks/ema200/oi5m_rule/OI_5M_RULE.md`.

Both legs already exist as `leg_change` (OpenSpec `o1-leg-change-v1`), and the division already exists as `ratio`. The only
missing piece is the absolute value: the impulse price change is negative on the short side.

## What Changes

- **New operand `abs`** `{"abs": <operand>}`: the absolute value of another operand, bar by bar. Missing where the inner operand is missing.
- **kI** is `ratio(leg_change {impulse, open_interest}, abs(leg_change {impulse, close}))` with `right_floor` 0, so the
  denominator only has to be greater than zero. The owner dropped research's `0.05` guard on 2026-10-26 at 20:00: on vote v7 under
  the Engine rule the result is the same to the dollar (11.7 / 9.1 / 8.4k). The Engine holds no number.
- **Cost**: one vectorised `abs` per bar; a spec without the operand pays nothing.

Not in this change: kR, W1, W2d, W8, nested ratios, the voting module, catalog and manifest bindings, deploy.
