## Why

Research metric **A5 "how straight the pullback is against the impulse"** (group A of the almanac), on Kaufman's efficiency ratio
of 5m closes: `ER(a, z) = |close[z] − close[a]| / Σ |close[k] − close[k−1]|` over `k = a+1..z`.

Vote B used the difference `ER(pullback) − ER(impulse)`. On 2026-10-22 the owner reviewed real cut entries (very short, straight
pullbacks that erase a crooked impulse) and decided to rewrite A5 as the **ratio** `ER(pullback) / ER(impulse)`. Its thresholds
(2.01, 2.28, 2.82, 2.96) are being simulated in the review thread; the Engine holds no threshold.

## What Changes

- **New operand `leg_efficiency`** `{episode, leg}`: the efficiency ratio of the closes of one leg of the current touch, the
  impulse over `[S*, P]` and the pullback over `[P, t]`. Missing without a valid wave, on a leg of one bar (`P = S*`, or `t = P` for
  the pullback, as research computes A5 only when `t > P`), when the closes do not move (`Σ = 0`) or a close is not finite.
- **A5** is `ratio(leg_efficiency(pullback), leg_efficiency(impulse))`; the existing `ratio` is missing when the impulse value is
  0, as research (`ER(impulse) > 0`). A difference would need a new operator; not in this change.
- **Cost**: O(bars), vectorised over prefix sums; a spec without the operand pays nothing.

Not in this change: a difference operator, catalog and manifest bindings, deploy.
