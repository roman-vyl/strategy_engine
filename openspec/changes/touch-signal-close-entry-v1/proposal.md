## Why

Owner decision 2026-10-27 (thread «Перевести вход на цену закрытия свечи касания», brief
`/mnt/project-files/engine-tasks/ema200/close_limit_entry/BRIEF.md`). Today live-entry returns a plan on every bar where
the setup is allowed and the close is on our side, at `entry = anchor[i]` (EMA). Runtime places it in advance for the
next bar, so every filter, the v8 vote included, is read on the bar *before* the touch. Research and the simulation enter
on the close of the touch bar, with every filter read on that same bar.

Simulation, working-zone medians, v8 θ1.5 (BTC / ETH / SOL / SOL W6 / SOL SL5.5-6.5): entry at the touch close
14.4 / 10.2 / 11.0 / 32.3 / 19.8k vs today's live scheme 7.2 / 6.9 / 6.0 / 45.7 / 11.3k
(`/mnt/project-files/ema200_calib/review/live/reclaim/`).

The owner split the work into stages. **This change is stage 1 only: the Engine → Runtime contract.** What Runtime does
with the plan next (order lifetime) and which order ABI places are later stages.

## What Changes

- New Engine config file, the same way MDS reads `BBB_data/mds/markets.toml`: path from
  `STRATEGY_ENGINE_CONFIG_PATH` (in the stack: `BBB_data/strategy-engine/engine.toml`, mounted read-only), read once at
  start. Key `live_entry_mode`. Change = edit the file + restart the Engine (no image, no pin, no deploy). Missing file or
  missing key = `ema_anchor`:
  - `ema_anchor` (default): today's live-entry, byte-identical.
  - `touch_trigger`: live-entry returns a plan for a target bar **only when that bar is a signal bar** of a side (the
    side's final entry is allowed on that bar: setups with the vote and blockers, touch with close on our side, risk).
    `planned_entry_price = close` of that bar; stop and take = `close ∓ / ± distance` from the exit policy on that bar;
    partial takes priced from the same entry. Any other bar returns `null`.
  - Any other value, an unknown key or a file that does not parse: the service refuses to start.
- The switch is engine-wide (every strategy served by this Engine) and changes **only the live-entry answer to Runtime**.
  `/range`, `/range-batch`, `/managed-replay`, `/open-trade`, `potential_entries` and research results stay unchanged.
- The live-entry response keeps exactly today's shape. No new field.

## Not in this change

- Runtime, ABI, bbb_stack. The mode MUST NOT be set to `touch_trigger` on a live (demo or real) stack before the ABI
  stage: ABI places a conditional Market entry today, and with a trigger at the last close it fires at once as a taker.
  Mounting the config folder in bbb_stack is a separate small change on the owner's word.
- Order lifetime, order type, post-only, fees.

## Impact

- `service/settings.py` (config path + TOML read + validation), `service/wiring.py` (pass the mode), `README.md`
  (Environment + config file), example `config/engine.toml.example`.
- `application/evaluate_live_entry_projection.py` passes the mode to the adapter;
  `strategies/live_projections/defaults.py` passes the mode to the adapter; `ema_pullback/live_projections/live_entry.py`
  builds the `touch_trigger` plan from the evaluation it already runs.
- No change to `potential_entries.py`, node identities, raw spec validation or HTTP models.
