## 1. Ratio

- [ ] 1.1 A ratio side may be a ratio; constants on both sides still rejected. Verify: parse tests.
- [ ] 1.2 Nested value equals `left / right` of the inner values with the outer `right_floor`, missing propagated, on both sides. Verify: tests.

## 2. W1r

- [ ] 2.1 `ratio(ratio(...), ratio(...), right_floor 0.05)` through the pipeline on the BTC fixture equals the loop (close-based legs, the fixture has no OI). Verify: e2e test.
- [ ] 2.2 Candidates differing only in a level share the inner ratios. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [ ] 3.1 W1r on all EMA200 entries of BTC, ETH and SOL against the D2 reference (1e-9 relative, NaN equal), research W1r compared and differences explained. Report in `/mnt/project-files/engine-tasks/ema200/parity_w1r/`.

## 4. Gate

- [ ] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [ ] 4.2 `openspec validate w1r-nested-ratio-v1 --strict`.
