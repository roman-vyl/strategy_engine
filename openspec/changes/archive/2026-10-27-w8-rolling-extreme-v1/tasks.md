## 1. Features

- [x] 1.1 `rolling_max` / `rolling_min` contracts: period, source enum with `open_interest`, label with source, identity; malformed requests rejected. Verify: tests.
- [x] 1.2 Values against pandas rolling with `min_periods=period` on OHLC and OI with gaps, on base and a higher timeframe (last completed candle). Verify: tests.
- [x] 1.3 Live warm-up of `period` candles. Verify: requirements test.

## 2. Operand

- [x] 2.1 `{price: open_interest}` parses and reads the bar's OI, missing where none. Verify: tests.

## 3. W8_14 / W8_30

- [x] 3.1 The ratio through the pipeline on the BTC fixture equals the loop (the fixture has no OI: field `close`, the OI column path is unit-tested); level candidates share nodes. Verify: e2e test.
- [x] 3.2 Parity on all EMA200 entries of BTC, ETH and SOL against `W8_14`, `W8_30` of `feat_<coin>.npz` (1e-9 relative, NaN equal). Report in `/mnt/project-files/engine-tasks/ema200/parity_w8/`.
  Result: exact on all entries (W8_14 BTC 2318, ETH 2414, SOL 2223; W8_30 2291 / 2386 / 2207; max relative 0); engine run 45-56 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate w8-rolling-extreme-v1 --strict`.
