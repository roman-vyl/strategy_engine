## 1. Operand

- [x] 1.1 Parse and validate `forming_candle`: required declared `episode`, `timeframe`, `atr` (`atr_wilder`, same timeframe); unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values against a brute-force loop on synthetic series: long and short, bars without a wave missing, ATR warm-up missing. Verify: tests.

## 2. D1

- [x] 2.1 `forming_candle 1d` through the pipeline on the BTC fixture equals the loop; a vote weight step acts exactly on the bars at or below its level. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the operand; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 D1 on all research entries of BTC, ETH, SOL against `d1_1d` (1e-9 relative, NaN equal), entries at ≤ −0.274 equal, run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_d1/`.
  Result: values equal on all entries with a research value (BTC 2811, ETH 2528, SOL 2223; max relative 0), entries at ≤ −0.274 equal (94 / 102 / 86); engine run 41-50 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate d1-forming-candle-v1 --strict`.
