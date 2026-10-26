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

### D3. Known difference from research

Research computes kI and kR in one expression. kI is therefore also missing where the pullback price move `rR <= 0.05` or the
entry bar has no OI. These are 9 / 16 / 3 entries of BTC / ETH / SOL out of about 2300 per coin. The atomic operand depends on
the impulse only, and parity reports these entries separately.
