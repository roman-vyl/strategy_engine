## 1. Operand

- [x] 1.1 Parse and validate `leg_efficiency`: required declared `episode` and `leg`; unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values against a loop written like research `er` on synthetic series: both legs, long and short, missing cases, no look-ahead. Verify: tests.

## 2. A5

- [x] 2.1 `ratio(leg_efficiency pullback, leg_efficiency impulse)` through the pipeline on the BTC fixture equals the loop; a vote weight step acts exactly on the bars at or above its level. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the operands; a spec without the operand has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud, on the owner's separate command)

- [ ] 3.1 A5 ratio on all research entries of BTC, ETH, SOL against the review thread simulation (1e-9 relative, NaN equal), entries at the chosen thresholds equal, run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_a5/`.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate a5-leg-efficiency-ratio-v1 --strict`.
