## 1. Operand

- [x] 1.1 Parse and validate `at_point`: all fields required, unknown fields rejected, `point` only `peak` or `origin`, constant and nested `at_point` inner rejected, accepted in `range`, `compare`, `ratio`, `difference`, `abs` and vote inputs, rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values equal `inner[P]` / `inner[S*]` on valid touch bars, missing elsewhere and where the inner value at the point is missing, both sides of the trade. Verify: tests.

## 2. W8p

- [x] 2.1 `at_point(peak, ratio(price, rolling_max))` through the pipeline on the BTC fixture equals the loop (close-based, the fixture has no OI). Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the nodes; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 W8p on all EMA200 entries of BTC, ETH and SOL against the D3 reference. Report in `/mnt/project-files/engine-tasks/ema200/parity_w8p/`.
  Result: exact on all entries (BTC 2291, ETH 2384, SOL 2207; max relative 0); no entry defined on one side only; engine run 32-39 s per coin.

## 4. Gate

- [ ] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate w8p-at-point-v1 --strict`.
