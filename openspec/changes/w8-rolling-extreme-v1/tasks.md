## 1. Features

- [ ] 1.1 `rolling_max` / `rolling_min` contracts: period, source enum with `open_interest`, label with source, identity; malformed requests rejected. Verify: tests.
- [ ] 1.2 Values against pandas rolling with `min_periods=period` on OHLC and OI with gaps, on base and a higher timeframe (last completed candle). Verify: tests.
- [ ] 1.3 Live warm-up of `period` candles. Verify: requirements test.

## 2. Operand

- [ ] 2.1 `{price: open_interest}` parses and reads the bar's OI, missing where none. Verify: tests.

## 3. W8_14 / W8_30

- [ ] 3.1 The ratio through the pipeline on a fixture with OI equals the loop; level candidates share nodes. Verify: e2e test.
- [ ] 3.2 Parity on all EMA200 entries of BTC, ETH and SOL against `W8_14`, `W8_30` of `feat_<coin>.npz` (1e-9 relative, NaN equal). Report in `/mnt/project-files/engine-tasks/ema200/parity_w8/`.

## 4. Gate

- [ ] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [ ] 4.2 `openspec validate w8-rolling-extreme-v1 --strict`.
