## 1. Setting
- [x] 1.1 `Settings.live_entry_mode` from TOML at `STRATEGY_ENGINE_CONFIG_PATH` (`ema_anchor` when absent | `touch_trigger`); unknown value/key or parse error fails at start
- [x] 1.2 Wiring passes the mode to `EvaluateLiveEntryProjection`; README Environment + config file, `config/engine.toml.example`

## 2. Live entry
- [x] 2.1 Mode injected into the EMA Pullback live-entry adapter via the default registry (protocol unchanged); `ema_anchor` path unchanged
- [x] 2.2 EMA Pullback `touch_trigger` plan: `entry_allowed[target]`, entry = close, stop/take from exit-policy distances, same checks, profile and partial takes; non-touch trigger → `null`

## 3. Tests (targeted only, `PYTHONPATH=src:.:tests`; never `tests/parity/test_all_families_memo.py`)
- [x] 3.1 Settings: no path, missing file, both values, invalid value, unknown key, broken TOML
- [x] 3.2 Unit: signal bar, armed bar without touch, vote-blocked touch, false break then return, bar after signal, short mirror, other trigger
- [x] 3.3 `ema_anchor` live-entry fixtures byte-identical; `/range` identical in both modes (the mode is injected only into the live-entry adapter; range/batch/managed never receive it)
- [x] 3.4 Parity on full history BTC/ETH/SOL working-zone cells: `touch_trigger` plan bars = `<side>_trigger` of `/mnt/project-files/ema200_calib/review/live/eng/<coin>_w<W>_lb<LB>.npz`, entry = close; `ema_anchor` = `<side>_entry` bit for bit. DONE 18 cells (BTC/ETH/SOL x6): plan bars, prices, stop/take and anchor plans all equal; `/mnt/project-files/engine-tasks/ema200/close_limit_entry/parity/`
- [x] 3.5 Replay plan → limit next bar → fill when reached, v8 θ1.5 (Engine v8 weighted_vote_setup output, main b48b657; 0 block diffs vs simulation): medians 14.4 / 10.2 / 11.0 / 32.3 / 19.8k, equal to the simulation; `/mnt/project-files/engine-tasks/ema200/close_limit_entry/replay/`
- [x] 3.6 Report: live open-trade replays from the bar after the fill bar (offset 1, fill bar = signal+1), research from the signal bar (offset 0): managed rules run one bar later live. EMA200 cells use fixed SL/TP without exit_management, so no effect there; matters only for managed strategies
