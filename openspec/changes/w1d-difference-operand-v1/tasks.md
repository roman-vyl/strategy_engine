## 1. Operand

- [ ] 1.1 Parse and validate `difference`: both sides required, unknown fields rejected, two constants rejected, ratio and difference sides accepted, accepted in `range`, `compare`, `ratio`, `abs` and vote inputs, rejected in `change`. Own node family. Verify: tests.
- [ ] 1.2 Values equal `left − right`, missing propagated, both sides of the trade. Verify: tests.

## 2. W1d

- [ ] 2.1 `difference(ratio(...), ratio(...))` through the pipeline on the BTC fixture equals the loop (close-based legs, the fixture has no OI). Verify: e2e test.
- [ ] 2.2 Candidates differing only in a level share the nodes; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [ ] 3.1 W1d on all EMA200 entries of BTC, ETH and SOL against the D3 reference (1e-9 relative, NaN equal), research W1d compared. Report in `/mnt/project-files/engine-tasks/ema200/parity_w1d/`.

## 4. Gate

- [ ] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [ ] 4.2 `openspec validate w1d-difference-operand-v1 --strict`.
