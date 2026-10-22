## 1. Operand

- [x] 1.1 Parse and validate `leg_speed`: required declared `episode` and `leg`; unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values against a brute-force loop on synthetic series: both legs, long and short, zero impulse height, non-finite close. Verify: tests.
- [x] 1.3 Only bars ≤ t are read. Verify: truncation test.

## 2. A3

- [x] 2.1 `ratio(leg_speed pullback, leg_speed impulse)` through the pipeline on the BTC fixture equals the loop; a vote weight step and a veto step act exactly on the bars at or above their levels. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the operands; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 A3 on all research entries of BTC, ETH, SOL against `a3` (1e-9 relative, NaN equal), entries at ≥ 3.33 and ≥ 15.8 equal, run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_a3/`.
  Result: values equal on all entries (BTC 2815, ETH 2534, SOL 2226; max relative 0), entries at ≥ 3.33 equal (344 / 220 / 204) and at ≥ 15.8 equal (32 / 13 / 5); engine run 39-48 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate a3-leg-speed-ratio-v1 --strict`.
