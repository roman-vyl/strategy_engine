## 0. Baseline

- [ ] 0.1 Branch from main 95162fd. V1.3, V2.2 and the weighted vote suites pass unchanged. Targeted tests only (`PYTHONPATH=src:.:tests`), never `tests/parity/test_all_families_memo.py`.

## 1. Parse and validate

- [ ] 1.1 `leg_sum` operand: required `episode`, `leg`, `field`; unknown fields rejected; `leg` in {impulse, pullback}; `field` = `volume`; undeclared episode rejected. Verify: tests.
- [ ] 1.2 Accepted as a side of a `ratio`, as the operand of a `range`, of a `compare` and of a weighted vote input; rejected as the operand of a `change`. Verify: tests.
- [ ] 1.3 Identity: own node family `predicate.leg_sum`; `leg_mean` identities and results unchanged. Verify: identity test.

## 2. Evaluation

- [ ] 2.1 Sums of `[S*, P]` and `[P+1, t]` against a brute-force loop on synthetic series: `t = P` (pullback missing), one-bar legs, several touches, a new episode, a non-finite volume in the leg. Verify: tests.
- [ ] 2.2 V1.1 as `ratio`: impulse sum 0 gives missing; value exactly on a vote level crosses it (inclusive). Verify: tests.
- [ ] 2.3 Only bars ≤ t are read (changing later volume leaves earlier values). Verify: truncation test.
- [ ] 2.4 Long and short give the same value. Verify: test.

## 3. Identity, sharing, cost

- [ ] 3.1 Candidates that differ only in a level share both operands and the ratio; `unforeseen_consumptions` stays 0. Verify: batch tests.
- [ ] 3.2 A spec without `leg_sum` has an identical node set and results. Verify: existing suites.

## 4. Parity with research on EMA200 (cloud)

- [ ] 4.1 With `run_engine.py` / `compare.py` of `/mnt/project-files/engine-tasks/ema200/parity/` (`window_bars` 24): V1.1 on all research entries of BTC, ETH, SOL against `v11` of research (1e-9 relative, NaN equal).
- [ ] 4.2 Entries crossing ≤ 0.0574 and ≤ 0.0441 per coin equal to research (working zones: 26 and 9).
- [ ] 4.3 Report the parity table; stop for the owner's review.

## 5. Gate

- [ ] 5.1 ruff, mypy, affected tests.
- [ ] 5.2 `openspec validate v1-volume-sum-ratio-v1 --strict`.
