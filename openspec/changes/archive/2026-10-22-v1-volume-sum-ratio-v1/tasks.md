## 0. Baseline

- [x] 0.1 Branch from main 95162fd. V1.3, V2.2 and the weighted vote suites pass unchanged. Targeted tests only (`PYTHONPATH=src:.:tests`), never `tests/parity/test_all_families_memo.py`.

## 1. Parse and validate

- [x] 1.1 `leg_sum` operand: required `episode`, `leg`, `field`; unknown fields rejected; `leg` in {impulse, pullback}; `field` = `volume`; undeclared episode rejected. Verify: tests.
- [x] 1.2 Accepted as a side of a `ratio`, as the operand of a `range`, of a `compare` and of a weighted vote input; rejected as the operand of a `change`. Verify: tests.
- [x] 1.3 Identity: own node family `predicate.leg_sum`; `leg_mean` identities and results unchanged. Verify: identity test.

## 2. Evaluation

- [x] 2.1 Sums of `[S*, P]` and `[P+1, t]` against a brute-force loop on synthetic series: `t = P` (pullback missing), one-bar legs, several touches, a new episode, a non-finite volume in the leg. Verify: tests.
- [x] 2.2 V1.1 as `ratio`: impulse sum 0 gives missing; value exactly on a vote level crosses it (inclusive). Verify: tests.
- [x] 2.3 Only bars ≤ t are read (changing later volume leaves earlier values). Verify: truncation test.
- [x] 2.4 Long and short give the same value. Verify: test.

## 3. Identity, sharing, cost

- [x] 3.1 Candidates that differ only in a level share both operands and the ratio; `unforeseen_consumptions` stays 0. Verify: batch tests.
- [x] 3.2 A spec without `leg_sum` has an identical node set and results. Verify: existing suites.

## 4. Parity with research on EMA200 (cloud)

- [x] 4.1 With `run_engine.py` / `compare.py` of `/mnt/project-files/engine-tasks/ema200/parity/` (`window_bars` 24): V1.1 on all research entries of BTC, ETH, SOL against `v11` of research (1e-9 relative, NaN equal).
- [x] 4.2 Entries crossing ≤ 0.0574 and ≤ 0.0441 per coin equal to research (working zones: 26 and 9).
- [x] 4.3 Report the parity table; stop for the owner's review.

Parity result (cloud, 2026-10-22, `/mnt/project-files/engine-tasks/ema200/parity_v11/`): on every research entry with a wave
(BTC 2815, ETH 2534, SOL 2226) V1.1 equals research `v11` exactly (max relative difference 0.0), empties equal. Entries at
≤ 0.0574: BTC 39 / ETH 21 / SOL 22, at ≤ 0.0441: 17 / 7 / 5, identical in research and Engine; the vote's veto equals the
threshold on the values everywhere.

## 5. Gate

- [x] 5.1 ruff, mypy, affected tests.
- [x] 5.2 `openspec validate v1-volume-sum-ratio-v1 --strict`.
