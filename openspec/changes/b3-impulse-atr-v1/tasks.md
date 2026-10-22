## 1. Operand

- [x] 1.1 Parse and validate `impulse_atr`: required declared `episode` and `atr` of kind `atr` on the base timeframe; unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family with the ATR column upstream. Verify: tests.
- [x] 1.2 Values against a brute-force loop on synthetic series: long and short, zero height, ATR missing at `P`. Verify: tests.
- [x] 1.3 Only bars ≤ t are read. Verify: truncation test.

## 2. B3

- [x] 2.1 Operand through the pipeline on the BTC fixture equals the loop with the rolling-mean ATR; a vote weight step and a veto step act exactly on the bars at or below their levels. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the operand; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 B3 (ATR 48) on all research entries of BTC, ETH, SOL against `b3h` (1e-9 relative, NaN equal), entries at ≤ 9.59 and ≤ 4.65 equal, run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_b3/`.
  Result: values equal on all entries (BTC 2815, ETH 2534, SOL 2226; max relative 0), entries at ≤ 9.59 equal (819 / 736 / 629) and at ≤ 4.65 equal (69 / 59 / 46); engine run 34-43 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate b3-impulse-atr-v1 --strict`.
