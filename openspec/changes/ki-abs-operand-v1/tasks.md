## 1. Operand

- [x] 1.1 Parse and validate `abs`: exactly one inner operand; constant, `abs` and `ratio` inside rejected; accepted in `ratio`, `range`, `compare` and vote inputs; rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values equal `np.abs` of the inner operand, missing kept, on both sides. Verify: tests.

## 2. kI

- [x] 2.1 `ratio(leg_change OI impulse, abs(leg_change close impulse), right_floor 0)` through the pipeline on the BTC fixture equals the loop (the fixture has no OI: numerator on the pullback `close` change). Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the nodes; a spec without `abs` has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 kI on all EMA200 entries of BTC, ETH and SOL against `O1 / rI` (`rI > 0`) built from `oi5m_rule/oi5m_ref_<coin>.csv.gz` O1 and the closes (1e-9 relative, NaN equal), entries with research `kI` missing for the D3 reasons reported, with run time. Report in `/mnt/project-files/engine-tasks/ema200/parity_ki/`.
  Result: exact on all entries (BTC 2331, ETH 2419, SOL 2218; max relative 0); engine value where research kI is empty 9 / 17 / 3 (D3); engine run 42-54 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate ki-abs-operand-v1 --strict`.
