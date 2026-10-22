## 1. Operand

- [x] 1.1 Parse and validate `leg_top_mean`: required `episode`, `leg`, `field`, `share`; `share` in (0, 1]; unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values against a brute-force loop on synthetic series: impulse and pullback, `t = P` missing, one-bar legs, several touches, non-finite volume, `k` with `ceil` in float64 (L = 30, share 0.1 → 3). Verify: tests.
- [x] 1.3 Only bars ≤ t are read. Verify: truncation test.

## 2. V1.4

- [x] 2.1 Ratio through the pipeline on the BTC fixture equals the loop; a vote veto step blocks exactly the bars at or below its level. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the operands; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 V1.4 on all research entries of BTC, ETH, SOL against `v14` (1e-9 relative, NaN equal), entries at ≤ 0.084 equal, run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_v14/`.
  Result: values equal on all entries (BTC 2815, ETH 2534, SOL 2226; max relative 8e-16), vetoes at ≤ 0.084 equal (6 / 9 / 5); engine run 44-56 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate v1-top-volume-ratio-v1 --strict`.
