## Context

- `touches` rows of the episode carry `peak_bar` and `peak_price` (unmirrored: the high of bar `P` on the long side, the low on the
  short side), and `candles.touch_points` gives the valid current touch on every bar. The episode is built from the stack's anchor
  EMA (EMA500 for a 200 / 500 / 1000 stack, EMA1000 for 500 / 1000 / 2000), `ewm(span = anchor, adjust = False)` on the 5m close.
- Research reference: `c5/c5_engine_ref.py` (Mac); reference rows carry p_bar, p_price, ema_p, ema_b, gap, ema_move, c5. Where this
  change and the reference differ, the reference wins.

## Decisions

### D1. A dedicated operand

`{"anchor_follow": {"episode"}}`, required `episode`, no other field. Rejected: building C5 from existing segments. A segment
aggregates a leg of a feature series, but C5 needs the anchor value at one bar (`P`), the anchor value at the evaluated bar, and the
peak price of the touch row, which is not a feature. A dedicated operand keeps the definition in one place and costs O(n).

### D2. The anchor

The anchor series is the anchor EMA the episode itself was built from, so it follows the stack by construction and the spec carries no
period. The spec declares nothing else: the same series is used for `EMA[P]` and `EMA[b]`.

### D3. Value

For the evaluated side, `g = +1` (long) or `−1` (short), `gap = g · (peak_price − EMA[P])`, `move = g · (EMA[b] − EMA[P])`,
`C5 = move ÷ gap`. For a short that is `gap = EMA[P] − low[P]` and `move = EMA[P] − EMA[b]`. Missing when there is no valid current touch,
when `gap ≤ 0` (never happens in the research data, guarded), or when `EMA[P]`, `EMA[b]` or `peak_price` is not finite.
`gap` and `move` are available as the trace parts together with `peak_price`, `EMA[P]` and `EMA[b]`.

### D4. Entry bar and lookahead

The value is evaluated on bar `t = b`, the signal bar, from data up to and including the close of `b`. `EMA[b]` is the anchor value on
`t`; `EMA[P]` and `peak_price` belong to a bar `P ≤ t`. Nothing after `t` is read.

### D5. Filter

`range(anchor_follow)` with `bounds exclusive`, `empty: pass`: blocked when `C5 ≤ low` or `C5 ≥ high`, both inclusive, each optional.
All thresholds are in the request; the Engine holds none.

### D6. Identity and cost

Own node family `predicate.anchor_follow` with the episode identity as upstream (the anchor series is part of the episode identity),
no labels. Candidates that differ only in a bound share the operand. O(n) per series per side.

### D7. Open point for the review

How the operand reads the anchor series: from the episode context (it is already an input of the episode) or by re-resolving the
strategy's `anchor_stack` anchor feature. The spec requires only that it is the same series; the choice is made in the implementation.
