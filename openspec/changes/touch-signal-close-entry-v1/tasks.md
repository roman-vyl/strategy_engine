## 1. Setting
- [ ] 1.1 `Settings.live_entry_mode` from `STRATEGY_ENGINE_LIVE_ENTRY_MODE` (`ema_anchor` default | `touch_trigger`), invalid value fails at start
- [ ] 1.2 Wiring passes the mode to `EvaluateLiveEntryProjection`; README Environment

## 2. Live entry
- [ ] 2.1 Live-entry adapter protocol takes the mode; `ema_anchor` path unchanged
- [ ] 2.2 EMA Pullback `touch_trigger` plan: `entry_allowed[target]`, entry = close, stop/take from exit-policy distances, same checks, profile and partial takes; non-touch trigger → `null`

## 3. Tests (targeted only, `PYTHONPATH=src:.:tests`; never `tests/parity/test_all_families_memo.py`)
- [ ] 3.1 Settings: default, both values, invalid value
- [ ] 3.2 Unit: signal bar, armed bar without touch, vote-blocked touch, false break then return, bar after signal, short mirror, other trigger
- [ ] 3.3 `ema_anchor` live-entry fixtures byte-identical; `/range` identical in both modes
- [ ] 3.4 Parity on full history BTC/ETH/SOL working-zone cells: `touch_trigger` plan bars = `<side>_trigger` of `/mnt/project-files/ema200_calib/review/live/eng/<coin>_w<W>_lb<LB>.npz`, entry = close; `ema_anchor` = `<side>_entry` bit for bit
- [ ] 3.5 Replay plan → limit next bar → fill when reached, v8 θ1.5: medians 14.4 / 10.2 / 11.0 / 32.3 / 19.8k
- [ ] 3.6 Report (no fix here): open-trade entry bar = fill bar vs research signal bar; the management shift on the parity cells
