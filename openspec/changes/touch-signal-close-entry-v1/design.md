## Context

`_touch_anchor` (triggers.py) gives `trigger = touch & close_ok` on one bar. `_untouched_anchor` (setups.py) opens a
3-bar window after the first touch. `_project_side` (potential_entries.py) today emits a plan on every bar with
`pre_trigger_allowed & close_ok` at `entry = anchor[i]`: a plan for the *next* bar, placed before the touch happens.
`live_entry.py::_plan_for_side` reads PotentialEntry at the target index (= the last committed bar).

## Decisions

### D1. Mode lives on the trigger, default keeps today
`components.trigger.entry_price ∈ {"anchor", "signal_close"}`, default `"anchor"`. Allowed only with
`component_id: "touch_anchor"`; any other value, or the key on another trigger, is a validation error (no silent
fallback). Rationale: the price is a property of how the touch trigger is turned into an order.

### D2. `signal_close` emits a plan only on the signal bar
Plan on bar `i` iff `entry_allowed[i]` of the side (`pre_trigger_allowed & touch & close_ok`, then the risk mask). No
plan on armed-but-untouched bars, so no order sits in advance and nothing is computed on bar `i−1`.
`entry = close[i]`; stop/take from the exit-policy distances on bar `i` (R = k × ATR on the touch bar, unchanged);
partial takes from the same entry. The existing geometry check stays (`stop < entry < take` long, mirrored short).

### D3. Order kind travels with the plan
`LiveEntryPlan` / `DesiredEntry` get `entry_order: "post_only_limit" | None`. `None` is serialized as an absent key
(same pattern as `partial_takes`). Engine does not know exchanges; the value says "rest at this price as maker, never
take", ABI maps it to Bybit. Lifetime (one bar after the signal bar) is implied by `source_plan_bar_open_time_ms` and is
enforced by Runtime's existing per-bar reconciliation (no plan on the next bar → Cancel; a new signal → Replace).

### D4. One bar of validity is not a new Engine field
Runtime already asks Engine on every committed bar. A `signal_close` plan exists only for its own signal bar, so the
next bar returns `null` (or a new plan) and Runtime cancels/replaces. No `valid_until` is added here.

## Risks

- Fill at the level: the simulation counts a fill when the next bar reaches the close. With "must trade through by one
  tick" the SOL controls fall almost by half (13.1 / 9.4 / 10.0 / 16.4 / 11.9k). Measured on demo after deploy, not here.
- A post-only order is rejected when the market has already crossed the price at placement; handled in ABI/Runtime.
