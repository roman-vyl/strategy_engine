## Context

- Research reference: `review/ema100/feat100.py` (5m rule substitution in `review/oi5/engine_rule/feat.py`):
  `rI = abs(100 * (cl[P] / cl[S] - 1))`, `kI = O1 / rI` where `rI > 0.05`.
- Per-entry reference under the agreed OI rule: `engine-tasks/ema200/oi5m_rule/oi5m_ref_<coin>.csv.gz` column `kI`.

## Decisions

### D1. Operand `abs`

`{"abs": <operand>}` wraps exactly one operand. The value is `|x|` bar by bar, missing where `x` is not finite. The inner operand
must not be a constant, an `abs` or a `ratio`, so it adds no new way to nest a ratio. `abs` is accepted wherever its inner operand
is accepted, including inside a `ratio`, and rejected as the operand of a `change`.

Rejected: a side sign (`g`) on `leg_change`. A pullback's price change is not always against the trade at the close, while the
research takes the plain absolute value of both legs.

### D2. Identity

Own node family `predicate.abs`. Its upstream is the inner operand's node, and its side is set when the inner operand reads the
episode. Two specs with the same inner operand share the node.

### D3. Guard and known difference from research

Research guards both price moves with `> 0.05` and computes kI and kR in one expression. kI is therefore missing there also where
the pullback move is small or the entry bar has no OI. The owner removed the `0.05` guard (2026-10-26 20:00, checked on vote v7:
no change). The config uses `right_floor` 0, and the atomic operand depends on the impulse only.

The parity reference is `O1 / rI` where `rI > 0`, computed from the agreed-rule O1 and the closes. Entries where research's own
`kI` is missing for the pullback or entry reasons are reported separately.

The W1r condition `kI > 0.05` is not a guard but meaning, and it stays. It belongs to the W1r change, not here.
