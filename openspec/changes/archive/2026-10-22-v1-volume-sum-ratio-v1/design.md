## Context

- `leg_means.py` (V1.3, V2.2) builds per bar the legs of the current touch from `touch_points` (S* = `origin_bar`, P = `peak_bar`)
  and a prefix sum of the field; the mean is `(total[end+1] − total[begin]) / (end − begin + 1)`.
- Research reference: `altvals.py` (`ema200_calib/*/code/`), `v11 = seg(cV, P+1, b) / seg(cV, S, P)` when `b > P` and the
  impulse sum is `> 0`. The legs are the same as V1.3 (`P+1..b` and `S..P`).
- The existing components already match research on EMA200 to 1e-9 with waves equal on 100 % of entries
  (`/mnt/project-files/engine-tasks/ema200/parity/README.md`, `ema_stack_episode.window_bars` 24). Its `run_engine.py` and
  `compare.py` are reused for the parity of this change.

## Decisions

### D1. Operand `leg_sum`

`{"leg_sum": {"episode", "leg", "field"}}`, all required, no other field. `field` is `volume`. Value =
`total[end+1] − total[begin]` over the leg from the same prefix sums as `leg_mean`. Missing when the touch has no valid wave,
the leg is empty or a bar of the leg has a non-finite field. Bars after `t` are not read.

Rejected: a field or an `aggregate` switch on `leg_mean`. A sum is not a mean, and an operand named "mean" that returns a sum would
mislead whoever reads a spec. The leg and prefix-sum code is shared, not duplicated: one helper returns the leg bounds and the sum,
`leg_mean` divides it by the bar count.

### D2. V1.1

`ratio(leg_sum(pullback, volume), leg_sum(impulse, volume))`. Impulse sum 0: `right > 0` is false, the ratio is missing and the entry
is not blocked. The ratio is side-independent (volume has no side). No threshold is held by the Engine; vote B puts 0.0574 → 0.66
and 0.0441 → veto into its config.

### D3. Identity and cost

Own node family `predicate.leg_sum` with params `leg` and `field`, upstream the episode and the market bars; labels not in the
identity. Candidates that differ only in a level share both operands and the ratio. O(n) per series.

### D4. Volume source

`MarketBar.volume` of the base series, the same series as V1.3 (equal to research `volume_value`, checked at V1.3 parity).
Research reads a forward-filled 5m grid (a missing bar has volume 0); a missing bar does not change a sum, so no difference is
expected. Any difference found at parity is reported.
