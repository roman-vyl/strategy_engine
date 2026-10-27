## 1. Operands

- [x] 1.1 Parse and validate `signed` and `only_if`: required fields, unknown fields rejected, constant inner rejected, `require` non-empty with range-shaped items (`empty` rejected), accepted in `range`, `compare`, `ratio`, `difference`, `abs`, `at_point` and vote inputs, rejected in `change`. Own node families. Verify: tests.
- [x] 1.2 Values: `signed` long = inner, short = `2·center − x`; `only_if` = inner where all requirements hold, missing elsewhere and where a requirement value is missing. Verify: tests.

## 2. Wk and D1v

- [x] 2.1 Wk and D1v compositions through the pipeline on the BTC fixture equal the loop. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the nodes; a spec without the operands has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 Wk and D1v on all EMA200 entries of BTC, ETH and SOL against the D4 reference. Report in `/mnt/project-files/engine-tasks/ema200/parity_wk_d1v/`.
  Result: exact on all entries (Wk BTC 2713, ETH 2386, SOL 2113; D1v 233 / 230 / 178; max relative 0); no gate disagreement; engine run 35-43 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate signed-only-if-operands-v1 --strict`.
