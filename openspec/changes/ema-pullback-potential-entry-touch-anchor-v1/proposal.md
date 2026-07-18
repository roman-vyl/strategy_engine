# Proposal: EMA Pullback potential entry for touch-anchor v1

## Why

The existing EMA Pullback range pipeline produces final entry masks only after the configured trigger has fired. A future live consumer needs an additional pre-trigger projection: while no position exists, it must be able to read the potential entry, initial stop, and initial take prices that are valid on each closed bar.

The current engine already calculates all required source data:

- `SideSetupEvaluation.pre_trigger_allowed` is the existing pre-trigger strategy gate;
- the anchor EMA is already present in the planned feature frame;
- the exit-policy pipeline already calculates the ATR or constant-USD distance used by initial stop and take rules.

The missing capability is a small vector projection that combines these existing results without changing final-entry semantics, trigger semantics, or the existing range-calculation pipeline.

## What changes

- Add a minimal immutable `PotentialEntry` vector model containing only `side`, `entry_price`, `stop_price`, and `take_price`.
- Add a touch-anchor potential-entry projector after the existing EMA Pullback calculations.
- Use `pre_trigger_allowed` only as an internal projector input; do not add a separate public `allowed`, `armed`, or `global_entry_allowed` field.
- Set the potential entry price to the current anchor EMA for `touch_anchor`.
- Preserve the selected raw initial stop/take distance inside exit-policy evaluation before legacy normalization to `distance / close`.
- Calculate potential absolute stop/take prices from the anchor and those raw distances, requiring anchor, distances, and derived prices to be finite and strictly greater than zero.
- Add an always-present `potential_entries` object to the strategy range result and HTTP serialization. Non-`touch_anchor` triggers return `{}`; `touch_anchor` returns enabled-side keys only.
- Keep all existing entries, exit-policy ratios, component evidence, managed replay behavior, and public endpoint semantics unchanged.

## Out of scope

- Runtime lifecycle or Runtime HTTP contracts;
- Abi order type, order creation, amendment, cancellation, fills, or partial fills;
- conversion of a filled potential entry into an open-trade seed;
- management of an open position;
- potential-entry semantics for `reclaim_anchor` or `strong_reclaim_anchor`;
- changing current `touch_anchor` trigger or final-entry behavior;
- changing backtest execution assumptions;
- adding hashes, plan IDs, labels, trigger type, or order type to `PotentialEntry`.
