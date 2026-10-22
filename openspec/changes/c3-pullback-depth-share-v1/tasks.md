## 1. Operand

- [x] 1.1 Parse and validate `pullback_depth`: required declared `episode`, unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values against a brute-force loop on synthetic series: long and short, `t = P`, several touches, zero impulse height, non-finite prices. Verify: tests.
- [x] 1.3 Only bars ≤ t are read. Verify: truncation test.

## 2. C3.1

- [x] 2.1 Operand through the pipeline on the BTC fixture equals the loop; a vote step weights exactly the bars at or above its level. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the operand; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 C3.1 on all research entries of BTC, ETH, SOL against `c31` (1e-9 relative, NaN equal), entries at ≥ 0.604 equal, run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_c31/`.
  Result: values equal on all entries (BTC 2815, ETH 2534, SOL 2226; max relative 0), entries at ≥ 0.604 equal (1316 / 1166 / 888); engine run 41-50 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate c3-pullback-depth-share-v1 --strict`.
