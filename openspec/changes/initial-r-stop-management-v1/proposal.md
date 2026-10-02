## Why

Break-even (`break_even_stop` gated by an `mfe_r` phase rule) is the
best managed exit found so far (SL3×8 + BE@6R). Its next steps, "after
6R protect +4R" and "trail the stop 2R behind the best price", are the
same mechanism with a different stop formula. Built as a separate
trailing system they would duplicate the lifecycle that already works:
phase activation, the monotonic stop ratchet, next-bar effectiveness,
stop arbitration and level-fill execution.

This change adds one stop-management component, `r_stop`, measured in
the trade's initial R (the frozen coordinate system `mfe_r` already
uses). Only the formula that proposes the next stop price is new.

## What Changes

- New stop-management component `r_stop` with two modes:
  - `lock`: `stop_R = lock_r` (`lock_r >= 0`), a one-time step to a
    fixed R level once the rule is active;
  - `trail`: `stop_R = MFE_R - trail_r` (`trail_r > 0`), recomputed
    every bar from the best price so far.
  Here `stop price = entry ± stop_R × initial_risk`, sign by side, and
  `initial_risk = |entry - initial_stop|` frozen at entry.
- Activation is the existing one: `activate_when.phase_at_least`, with
  the trigger expressed as a phase rule (typically `mfe_r >= trigger`).
- The candidate joins the existing ratchet: the tightest active
  candidate wins and the active stop never moves back. A candidate not
  tighter than the initial stop is ignored.
- `break_even_stop` is kept unchanged as the compatible shorthand:
  `break_even_stop{buffer_type: none, buffer: 0}` and
  `r_stop{mode: lock, lock_r: 0}` give the same stop price on every
  bar of a trade with an initial stop.
- `ManagedStopActionRule` gains an optional `stop_basis`
  (`lock_r | trail_r`), omitted for every existing component, so
  existing projections and their hashes are unchanged.
- No feature, no history window, no extra indicator work; per bar one
  multiplication per active rule.

## Out of scope

- Runtime, AB Executor Bot and the deployed stack.
- ATR- or percent-based trailing, trailing from the close, and
  trailing that may loosen.
- A trigger inside the stop component (the trigger stays a phase rule).

## Impact

- `ema-pullback-managed-policy-v1`: ADDED `r_stop`.
- `historical-managed-projection-v1`: ADDED stop basis.
- Research Service consumes `stop_basis` in its own change
  (`initial-r-stop-management-v1`).
