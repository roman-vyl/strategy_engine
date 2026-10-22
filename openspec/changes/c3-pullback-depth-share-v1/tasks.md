## 1. Operand

- [ ] 1.1 Parse and validate `pullback_depth`: required declared `episode`, unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [ ] 1.2 Values against a brute-force loop on synthetic series: long and short, `t = P`, several touches, zero impulse height, non-finite prices. Verify: tests.
- [ ] 1.3 Only bars ≤ t are read. Verify: truncation test.

## 2. C3.1

- [ ] 2.1 Operand through the pipeline on the BTC fixture equals the loop; a vote step weights exactly the bars at or above its level. Verify: e2e test.
- [ ] 2.2 Candidates differing only in a level share the operand; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [ ] 3.1 C3.1 on all research entries of BTC, ETH, SOL against `c31` (1e-9 relative, NaN equal), entries at ≥ 0.604 equal, run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_c31/`.

## 4. Gate

- [ ] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [ ] 4.2 `openspec validate c3-pullback-depth-share-v1 --strict`.
