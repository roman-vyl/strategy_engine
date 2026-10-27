## 1. Operand

- [x] 1.1 Parse and validate `window_change`: all fields required, unknown fields rejected, `of` a base-timeframe feature, `last_n` a positive integer, `form` only `change` or `slope`, accepted in `range`, `compare`, `ratio`, `difference`, `abs`, `at_point` and vote inputs, rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values equal the D1 formula on valid touch bars, clipped at P, missing elsewhere, both sides of the trade, no look-ahead. Verify: tests.

## 2. The three EMA values

- [x] 2.1 The three compositions through the pipeline on the BTC fixture equal the loop. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the nodes; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [ ] 3.1 The three values on all EMA200 entries of BTC, ETH and SOL against the D3 reference. Report in `/mnt/project-files/engine-tasks/ema200/parity_ema_slope/`.
  Status: Engine equals the research formula with the window ending at the evaluated bar (BTC 2815, ETH 2534, SOL 2226 entries; max relative 4.5e-9 from the EMA seed). The reference file ends the window one bar earlier (b = bar - 1); which end to use is open with the owner.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate ema-slope-window-change-v1 --strict`.
