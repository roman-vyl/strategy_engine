## Context

- Research: `review/ema100/feat100.py`: `W1d = kR − kI`, where both moves are > 0.05. The owner dropped those guards on
  2026-10-26 at 20:00, so the Engine config uses `right_floor` 0.
- The segment operand already has an `of: {difference: {left, right}}` over two features. That is a feature-level input of a
  segment, not an operand, and it stays as is.

## Decisions

### D1. Operand `difference`

`{"difference": {"left", "right"}}`, both required, no other field. Each side is any operand of the layer. Both sides being
constants is rejected. Value `left − right`, missing where either side is not finite. It is accepted wherever a ratio is
accepted, and rejected as the operand of a `change`. `abs` may wrap a difference.

Rejected: a `sign` field on `ratio`. Subtraction is its own operation with its own node, as division is.

### D2. Identity

Own node family `predicate.difference`, with upstream `left` and `right` like a ratio. Its side is set when either side reads
the episode.

### D3. Parity reference

W1d = kR − kI, with kI = O1 / rI and kR = O2 / rR (moves > 0) under the 5m OI rule. Research W1d (with the 0.05 move guards) is
compared, and extra Engine values from the dropped guards are reported.
