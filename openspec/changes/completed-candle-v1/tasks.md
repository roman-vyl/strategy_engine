## 1. Operand

- [x] 1.1 Parse and validate `completed_candle`: required declared `episode`, `timeframe`, `field` (`body` / `close_position`), `atr` (`atr_wilder`, same timeframe); unknown fields rejected; accepted in `ratio`, `range`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values against a brute-force loop written like the research reference: hourly and weekly candles, long and short, both fields, bars without a wave and the first candle missing, zero ATR or range missing, no look-ahead. Verify: `tests/test_ema_pullback_completed_candle.py`.
- [x] 1.3 Weekly feature candles start on Monday and align from the next Monday. Verify: test.

## 2. Parity with research on EMA200 (cloud)

- [x] 2.1 Yesterday's body and close position (1d), the previous week's body (1w) and D1v composed as research (`body ≥ 1 and close_position ≥ 0.85`, else 9) on all research entries of BTC, ETH, SOL, 1e-9 relative. Report in `/mnt/project-files/engine-tasks/ema200/parity_cc/`.
  Result: all equal, max relative 0. Body BTC 2811 / ETH 2528 / SOL 2223, close position 2815 / 2534 / 2226, Wk 2713 / 2384 / 2113, D1v 2811 / 2528 / 2223; D1v ≤ −0.2 cuts 86 / 96 / 65 in both. Research has a value on a few entries without a wave (0-9 per coin), where D1 is missing too. Engine run 40-52 s per coin.

## 3. Gate

- [x] 3.1 ruff, mypy, affected tests (733 passed), never `tests/parity/test_all_families_memo.py`.
- [x] 3.2 `openspec validate completed-candle-v1 --strict`.
