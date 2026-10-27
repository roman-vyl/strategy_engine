## Why

Research metric **W1d "open interest on the pullback minus open interest in the impulse"** of vote W8 for EMA200:
`W1d = kR − kI`. Here kI = O1 / rI (OpenSpec `ki-abs-operand-v1`) and kR = O2 / rR (a composition of existing operands, parity exact).
Unlike W1r it is a difference, so it also reads impulses where open interest fell (`kI ≤ 0`). Research has no `kI > 0.05`
condition for W1d. Agreed with the owner on 2026-10-26 (20:44, «Да»).

Both sides already exist. The only missing piece is subtraction of two operands.

## What Changes

- **New operand `difference`** `{"difference": {"left", "right"}}`: `left − right` bar by bar. It is missing where either side is
  missing or non-finite. Sides may be any operand of the layer, ratios and differences included, but not both constants.
- **W1d** is `difference(kR, kI)` in the config. The Engine holds no number.
- The same operand will also give W2d (`O1` of the current wave minus `O1` of the previous wave) with `leg_change` `touch: previous`.
- **Cost**: one vectorised subtraction per bar; a spec without the operand pays nothing.

Not in this change: W2d parity, W8, the voting module, deploy.
