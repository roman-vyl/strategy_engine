## Why

Owner decision 2026-10-27 (thread «Перевести вход на цену закрытия свечи касания», brief
`/mnt/project-files/engine-tasks/ema200/close_limit_entry/BRIEF.md`). Today `potential_entries` gives a plan on every bar
where the setup is allowed and the close is on our side, at `entry = anchor[i]` (EMA). Runtime places that plan in
advance for the next bar, so every filter, the v8 vote included, is read on the bar *before* the touch. Research and the
simulation enter on the close of the touch bar, with every filter read on that same bar.

Simulation, working-zone medians, v8 θ1.5 (BTC / ETH / SOL / SOL W6 / SOL SL5.5-6.5): entry at the touch close
14.4 / 10.2 / 11.0 / 32.3 / 19.8k vs today's live scheme 7.2 / 6.9 / 6.0 / 45.7 / 11.3k
(`/mnt/project-files/ema200_calib/review/live/reclaim/`).

The owner split the work into stages. **This change is stage 1 only: the Engine → Runtime contract.** The Engine learns to
return the desired entry on the touch signal bar at that bar's close. What Runtime does with it next (order lifetime) and
which order ABI places are separate later stages.

## What Changes

- New optional key `components.trigger.entry_price` for the `touch_anchor` trigger: `"anchor"` (default, today's
  behavior) or `"signal_close"`.
- In `signal_close` mode a side's PotentialEntry exists on bar `i` **only when that side's entry is allowed on bar `i`**
  (`entry_allowed[i]`: all setups with the vote and blockers allowed, AND touch & close on our side on bar `i`). Then
  `entry = close[i]`; stop and take are `close[i] ∓ / ± distance[i]` from the exit policy on bar `i`; partial takes are
  priced from the same entry. On every other bar the side has no plan, so live-entry returns `null`.
- The live-entry response keeps exactly today's shape (side, source plan bar, planned entry, stop, take, locked profile,
  optional partial takes). No new field.
- Unchanged: the touch rule, the setup window (`untouched_anchor.active_bars`, default 3), every filter and the vote,
  exit distances, open-trade, managed replay, research execution (it already enters on the signal-bar close).

## Not in this change

- Runtime and ABI. The mode MUST NOT be enabled in a live (demo or real) strategy spec until the ABI stage: ABI places a
  conditional Market entry today, and with a trigger at the last close it would fire at once as a taker.
- Order lifetime, order type, post-only, fees.

## Impact

- `strategies/ema_pullback/potential_entries.py` (mode), `raw_spec_identity.py` / trigger validation (new key),
  `evaluation.py` (pass the entry mask and closes to the projection); tests.
- `live_projections/live_entry.py`, HTTP models, Runtime contract: no code change; they read the new values.
- Node identities: the trigger mask does not depend on `entry_price` and potential entries are outside the node families,
  so no identity changes. `/range` `potential_entries` in `signal_close` mode return the close-based prices.
