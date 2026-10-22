## 1. Operand

- [x] 1.1 Parse and validate `leg_bars`: required declared `episode` and `leg`; unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values against a brute-force loop on synthetic series: both legs, long and short, bars without a wave missing. Verify: tests.

## 2. A4

- [x] 2.1 `ratio(leg_bars pullback, leg_bars impulse)` through the pipeline on the BTC fixture equals the loop; a vote weight step acts exactly on the bars at or above its level. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the operands; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 A4 on all research entries of BTC, ETH, SOL against `a4` (1e-9 relative, NaN equal), entries at ≥ 10.3 equal, run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_a4/`.
  Result: values equal on all entries (BTC 2815, ETH 2534, SOL 2226; max relative 0), entries at ≥ 10.3 equal (54 / 51 / 34); engine run 43-51 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate a4-leg-bars-ratio-v1 --strict`.
