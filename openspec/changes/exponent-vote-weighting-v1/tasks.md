## 0. Baseline

- [x] 0.1 Code after the owner's «apply», on `main` after PR #49 is merged (or rebased on `claude/project-thread-teko29`, which has the
      W8 operands and `window_change`). Targeted suites (vote, setups, predicates, identity, feature plan) pass before and after every
      group. Never run `tests/parity/test_all_families_memo.py`. `PYTHONPATH=src:.:tests`.
      2026-10-27: coded on `claude/project-thread-a374gu` from main f3b9d37 (vote code does not depend on PR #49); rebase onto main
      after #49 is merged, before the variant 8 config and parity. Tests: `tests/test_ema_pullback_vote_exponent.py` (29) and
      `tests/test_ema_pullback_weighted_vote.py` unchanged and green.

## 1. Parse and validate

- [x] 1.1 `between` `step`|`linear`: linear needs ≥ 2 weight steps, no veto, no `direction`. Verify: tests.
- [x] 1.2 `weighting.exponent {k, e_v}`: > 0, finite, no booleans, overflow guard, only in `vote` voters, no veto step. Verify: tests.
- [x] 1.3 No side in the vote: `short` and `when` rejected as unknown fields (owner 10:36). Verify: tests.

## 2. Evaluate

- [x] 2.1 Linear ladder as `numpy.interp` with end values; missing → 0. Verify: scenario tests.
- [x] 2.2 Exponent `(exp(k·x) − 1)/(exp(k·e_v) − 1)`; bit equality with the research lambda on random values. Verify: tests.
- [x] 2.4 Exact rational score with exponent inputs; integer path unchanged otherwise; permuted voters give identical masks.

## 3. Evidence and identity

- [x] 3.1 Trace `input:<id>:level_value`. Verify: tests.
- [x] 3.2 Identity includes the new keys; vote B identities unchanged. Verify: tests.

## 4. Variant 8 config

- [ ] 4.1 Vote config for BTC/ETH/SOL from the design table: black-curve corner points (negative clipped to 0), k, e_v, θ 1.5, nine
      vote-B vetoes. No W8_60 (not in the v7/v8 chain). Wk and D1v join only once their operands give values "our way".
      vol1h = slot until the owner decides the volume source.

## 5. Parity (on the owner's command)

- [ ] 5.1 Engine in-process on full history, all entries BTC/ETH/SOL: blocked mask equals
      `/mnt/project-files/engine-tasks/ema200/vote_v8/engine_curves/blocked_theta1.5_<c>.npz` (BTC 923, ETH 774, SOL 883; keys
      `blocked`, `score`, `veto`); score equals `score` within 1e-12. Report entries with score in [θ − 1e-9, θ). Without vol1h, compare
      with the reference score minus the vol1h weights. Expected working-zone medians BTC 13.3k, ETH 9.9k, SOL 10.8k.
