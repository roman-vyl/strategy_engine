## 1. Spec and validation
- [ ] 1.1 Accept `components.trigger.entry_price` (`anchor` default | `signal_close`) for `touch_anchor` only; reject other values and other triggers
- [ ] 1.2 Keep trigger node identity independent of `entry_price`

## 2. Potential entries
- [ ] 2.1 `signal_close`: plan only on `entry_allowed[i]`, entry = `close[i]`, stop/take from distances on bar `i`
- [ ] 2.2 `anchor`: unchanged code path

## 3. Live entry
- [ ] 3.1 No change to `live_entry.py` / HTTP models; tests prove the response shape is unchanged in both modes

## 4. Tests (targeted only, `PYTHONPATH=src:.:tests`; never `tests/parity/test_all_families_memo.py`)
- [ ] 4.1 Unit: touch bar, armed bar without touch, vote-blocked touch, false break, short mirror, validation errors
- [ ] 4.2 Anchor mode byte-identical live-entry and `/range` fixtures
- [ ] 4.3 Parity on full history BTC/ETH/SOL working-zone cells: plan bars = `<side>_trigger` of `/mnt/project-files/ema200_calib/review/live/eng/<coin>_w<W>_lb<LB>.npz`, entry = close; anchor mode = `<side>_entry` bit for bit
- [ ] 4.4 Replay plan → limit next bar → fill when reached, v8 θ1.5: medians 14.4 / 10.2 / 11.0 / 32.3 / 19.8k
- [ ] 4.5 Report (no fix here): open-trade entry bar = fill bar vs research signal bar; measure the management shift on the parity cells
