## 1. Operand

- [x] 1.1 Parse `touch` (`current` default, `previous`), reject other values; identity params `{}` for current, `{"touch": "previous"}` for previous. Verify: tests.
- [x] 1.2 Previous values against a brute-force loop on synthetic series: long and short, first touch missing, `S* ≤ P0`, zero previous height, non-finite prices. Verify: tests.
- [x] 1.3 Only bars ≤ t are read. Verify: truncation test.

## 2. C3.2

- [x] 2.1 `ratio(current, previous, right_floor 1e-6)` through the pipeline on the BTC fixture equals the loop; a vote veto step blocks exactly the bars at or above its level. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the operands; current-depth identity unchanged. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 C3.2 on all research entries of BTC, ETH, SOL against `c32` (1e-9 relative, NaN equal), entries at ≥ 3.43 equal, run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_c32/`.
  Result: values equal on all entries (BTC 1928, ETH 1680, SOL 1461 with a value, none only on one side; max relative 0), vetoes at ≥ 3.43 equal (18 / 5 / 7); engine run 45-53 s per coin.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate c3-previous-depth-ratio-v1 --strict`.
