## 1. Operand

- [ ] 1.1 Parse and validate `leg_change`: declared `episode`, `leg`, `field`; `touch` `current` | `previous`; `previous` only with `impulse`; unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [ ] 1.2 Values against a brute-force loop on synthetic series: both legs, both fields, current and previous touch, long and short, missing OI at an end, non-positive begin. Verify: tests.

## 2. O1

- [ ] 2.1 `leg_change {impulse, open_interest}` through the pipeline on the BTC fixture with an OI column equals the loop. Verify: e2e test.
- [ ] 2.2 Candidates differing only in a level share the operand; a spec without it has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [ ] 3.1 O1 on all research entries of BTC, ETH, SOL against `O1` in `review/oi5/engine_rule/feat_<coin>.npz` (1e-9 relative, NaN equal except D3), run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_o1/`.

## 4. Gate

- [ ] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [ ] 4.2 `openspec validate o1-leg-change-v1 --strict`.
