## 1. Operand

- [x] 1.1 Parse and validate `leg_change`: declared `episode`, `leg`, `field`; `touch` `current` | `previous`; `previous` only with `impulse`; unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [x] 1.2 Values against a brute-force loop on synthetic series: both legs, both fields, current and previous touch, long and short, missing OI at an end, non-positive begin. Verify: tests.

## 2. O1

- [x] 2.1 `leg_change` through the pipeline on the BTC fixture equals the loop, with a weight step and a veto step. Verify: e2e test.
  The fixture has no open interest, so the pipeline is checked on `close`; the operand reading `open_interest` from the market arrays has a unit test.
- [x] 2.2 Candidates differing only in a level share the operand; a spec without it has no such node. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 O1 on all research entries of BTC, ETH, SOL against `O1` in `review/oi5/engine_rule/feat_<coin>.npz` (1e-9 relative, NaN equal except D3), run time reported. Report in `/mnt/project-files/engine-tasks/ema200/parity_o1/`.
  Result: exact on all entries (BTC 2334, ETH 2433, SOL 2226; max relative 0); cuts at <= -5 and <= -10 equal (99/116/148, 29/38/32); no D3 case; engine run 40-47 s per coin.

## 4. Gate

- [ ] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate o1-leg-change-v1 --strict`.
