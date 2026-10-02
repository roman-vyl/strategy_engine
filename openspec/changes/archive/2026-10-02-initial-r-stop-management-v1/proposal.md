## Why

Managed stop policy can currently express break-even and ATR-based entry offsets, but it cannot express protection in the trade's frozen initial-R coordinate or a true stop that follows monotonic MFE. The recently shipped `mfe_r` trade state provides the missing frozen risk basis, so initial-R lock and trailing stops can now reuse the existing managed lifecycle without introducing a parallel execution path.

## What Changes

- Add distinct managed stop components for a one-time initial-R profit lock and a true MFE-following initial-R trailing stop.
- Define trigger, candidate-price, validation, tighten-only, long/short, and next-bar-effective semantics using the frozen `initial_risk` already owned by managed trade state.
- Extend the historical managed projection with a closed `stop_formula` execution semantic and opaque distance references. Legacy stop actions that omit `stop_formula` retain the existing `entry_offset` meaning and wire shape.
- Thread the already-supported optional `initial_stop_price` through the public managed-replay request so R-dependent policy can be replayed explicitly; requests that omit it remain valid and R-dependent rules fail closed.
- Preserve `break_even_stop` and `lock_profit_stop` as compatible legacy public components. In particular, unbuffered BE remains mathematically equivalent to `initial_r_lock_stop(trigger_r=N, lock_r=0)` when activation gates are equivalent.
- Add parity, compatibility, validation, long/short, monotonic-ratchet, and timing coverage. No indicator feature or additional live history window is introduced.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `ema-pullback-managed-policy-v1`: define initial-R lock/trailing components, frozen-risk candidate formulas, validation, arbitration, managed-replay input, and next-bar semantics.
- `historical-managed-projection-v1`: add the closed stop execution formula and opaque references required for Research to execute R-based stops without receiving component ids or raw strategy parameters.
- `live-calculation-window-planning`: classify both new stop components as zero-lookback managed rules.

## Impact

- Engine managed replay and live start-after-entry evaluation.
- Historical managed projection contracts and HTTP serialization.
- Public managed-replay request model and application plumbing.
- Managed-policy feature/history planning and focused parity/invariant tests.
- Coordinated Research Service change `initial-r-stop-management-v1` is required to decode and execute the new projection formulas.
