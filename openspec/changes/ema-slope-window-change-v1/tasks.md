## 1. Operand

- [ ] 1.1 Parse and validate `window_change`: all fields required, unknown fields rejected, `of` a base-timeframe feature, `last_n` a positive integer, `form` only `change` or `slope`, accepted in `range`, `compare`, `ratio`, `difference`, `abs`, `at_point` and vote inputs, rejected in `change`. Own node family. Verify: tests.
- [ ] 1.2 Values equal the D1 formula on valid touch bars, clipped at P, missing elsewhere, both sides of the trade, no look-ahead. Verify: tests.

## 2. The three EMA values

- [ ] 2.1 The three compositions through the pipeline on the BTC fixture equal the loop. Verify: e2e test.
- [ ] 2.2 Candidates differing only in a level share the nodes; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [ ] 3.1 The three values on all EMA200 entries of BTC, ETH and SOL against the D3 reference. Report in `/mnt/project-files/engine-tasks/ema200/parity_ema_slope/`.

## 4. Gate

- [ ] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [ ] 4.2 `openspec validate ema-slope-window-change-v1 --strict`.
