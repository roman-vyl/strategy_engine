## Why

The current Engine can measure an EMA change over the end of a pullback, but cannot faithfully express fixed pre-entry windows or endpoint changes of a normalized EMA-gap series. Research also permits signed denominators; substituting the existing positive-only ratio silently changes missing values and votes.

## What Changes

- Add a composable `interval_change` operand: select a fixed window or a current episode leg, optionally restrict the leg to its last N bars, and measure endpoint change, change per bar, relative change, or relative change per bar.
- Accept a bounded grammar of causal base-timeframe arithmetic series as its input, reusing existing feature, price, difference, ratio and abs operands; add a generic `scale` operand for explicit units.
- Add opt-in absolute-magnitude denominator validation to ratio. Preserve positive-only behavior by default.
- Integrate parsing, feature planning, causal history requirements, dependency sharing, identities and diagnostics. Preserve old window_change behavior and old strategy identities.
- No filter IDs, EMA periods, calibration curves, trading thresholds or NVS3-specific logic in Engine.
- Explicitly out of scope: SPOT/PERP sourcing or alignment, new market streams, voting-rule changes, filter selection, calibration, deployment and profitability optimization.

## Capabilities

### New Capabilities

- `interval-series-operands-v1`: composable endpoint measurements over fixed and episode intervals, explicit scaling, and opt-in signed division; planning and compatibility obligations.

### Modified Capabilities

- `pre-entry-predicates-v1`: extend ratio with an explicit denominator mode, retaining its existing default.

## Impact

Engine ema_pullback operand parsing/evaluation, feature planner, static semantics, live history planner, memo identities and requirement traversal, public strategy schema/catalog documentation, and tests. Existing weighted_vote_setup consumes the resulting operand without a new voting implementation. Research supplies reference formulas and parity fixtures; surface manifests are a later integration step. No new dependencies or market-data contract changes.
