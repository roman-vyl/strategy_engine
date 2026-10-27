## Why

Owner decision 2026-10-27 (thread «Независимое ревью фильтров EMA200», brief
`/mnt/project-files/engine-tasks/ema200/close_limit_entry/BRIEF.md`): the live entry for EMA200 must be the
**close of the touch bar**, not the EMA value. Today `potential_entries` puts `entry = anchor[i]` on every bar where the
setup is allowed and the close is on our side, so Runtime places a conditional order at the EMA in advance for the next
bar, and all filters (vote v8 included) are read on the bar *before* the touch. The research and the simulation enter on
the close of the touch bar with all filters read on that same bar.

Simulation, working-zone medians, v8 θ1.5 (BTC / ETH / SOL / SOL W6 / SOL SL5.5-6.5):
- new scheme (limit at touch close, alive one bar, maker, filled when price reaches it): 14.4 / 10.2 / 11.0 / 32.3 / 19.8k
- today's live scheme (EMA in advance, filters on bar n−1): 7.2 / 6.9 / 6.0 / 45.7 / 11.3k

Scripts: `/mnt/project-files/ema200_calib/review/live/reclaim/` (sim2, sim4, sim5, split, chk_eng2).

## What Changes

- New optional key `components.trigger.entry_price` for the `touch_anchor` trigger: `"anchor"` (default, today's
  behavior, byte-identical) or `"signal_close"`.
- In `signal_close` mode the side's PotentialEntry exists on bar `i` **only when an entry fired on bar `i`**
  (`entry_allowed[i]`: setup with vote and blockers allowed, AND `touch & close_ok` on bar `i`). Then
  `entry = close[i]`, `stop = entry ∓ SL_distance[i]`, `take = entry ± TP_distance[i]`; partial takes are priced from the
  same entry, as today.
- A `DesiredEntry` from a `signal_close` plan carries a new key `entry_order: "post_only_limit"`. The key is absent in
  `anchor` mode, so today's responses stay byte-identical and the order kind keeps meaning "conditional order at the
  planned price". The order kind belongs to the strategy spec, not to an ABI-wide setting, because both modes must run
  side by side on the same stack (the 8 demo strategies stay on `anchor`).
- The setup window (`untouched_anchor.active_bars`, default 3), the touch rule and every filter are unchanged.

Not in this change: Runtime and ABI handling of `entry_order` (separate changes `entry-order-kind-passthrough-v1` in
strategy_runtime and `abi-post-only-limit-entry-v1` in abi_executor_bot); research_service (it already enters at the
signal-bar close, `execution/entry.py::entry_decision_at`); vol1h and the v8 config (other threads).

## Impact

- `strategies/ema_pullback/potential_entries.py`, `live_projections/live_entry.py`, `strategies/contracts.py`
  (`LiveEntryPlan`, `DesiredEntry`), `application/evaluate_live_entry_projection.py`, `adapters/http/models.py` and
  `strategy_routes.py` (optional `entry_order`), spec validation of `components.trigger`; tests.
- Node identities: the trigger mask does not depend on `entry_price`, potential entries are outside the node families, so
  no identity changes. `/range` `potential_entries` in `signal_close` mode return the close-based prices.
- Deploy order: Runtime and ABI must understand `entry_order` **before** an Engine that emits it is deployed (Runtime
  decodes `desired_entry` as a closed object and would reject the new key).
