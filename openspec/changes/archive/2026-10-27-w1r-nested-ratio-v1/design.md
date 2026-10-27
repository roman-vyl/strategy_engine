## Context

- Research: `review/ema100/feat100.py`: `W1r = kR / kI` where `kI > 0.05` (and `rI, rR > 0.05`; the owner dropped those two
  guards on 2026-10-26 at 20:00, keeping `kI > 0.05`).
- Parser: `_ratio` rejects a ratio side; evaluation (`_ratio_operand`) and identity (`_resolve_operand`) already recurse through
  `_values` / `_resolve_operand`, so a ratio side is evaluated and identified like any other operand.

## Decisions

### D1. Allow nesting

Remove the nested-ratio check from `_ratio`. Constants on both sides stay rejected, and `abs` still rejects a ratio inside it.
The depth is bounded only by the spec. The inner ratio's node is the upstream of the outer one, so a ratio shared by several
parents is computed once.

### D2. Parity reference

W1r = kR / kI where kI > 0.05 and both are finite; kI and kR as in their parity (5m OI rule, guards `> 0`). Entries where
research's W1r differs only because of the dropped `0.05` move guards are reported separately.
