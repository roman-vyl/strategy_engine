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

- [x] 4.1 Vote config for BTC/ETH/SOL from the design table: black-curve corner points (negative clipped to 0), k, e_v, θ 1.5, nine
      vote-B vetoes. No W8_60 (not in the v7/v8 chain). Wk = `signed` (1w candle_body_atr, center 0), D1v = `only_if` (forming 1d, require signed body ≥ 1 and signed close position ≥ 0.85), teko29 7c684da; example `/mnt/project-files/engine-tasks/ema200/parity_wk_d1v/run_engine_wkd1v.py`.
      vol1h = `rolling_sum` volume ratio, teko29 df26588. The config is strategy data, not Engine code: base config by the review thread
      `/mnt/project-files/ema200_calib/review/live/vote_review/v8_vote_config_review.json` (owner 15:48: the Engine handles any config of this form).

## 5. Parity (on the owner's command)

- [x] 5.1 Engine in-process on full history, all entries BTC/ETH/SOL: blocked mask equals
      `/mnt/project-files/engine-tasks/ema200/vote_v8/engine_curves/blocked_theta1.5_<c>.npz` (BTC 923, ETH 774, SOL 883; keys
      `blocked`, `score`, `veto`); score equals `score` within 1e-12. Report entries with score in [θ − 1e-9, θ). Without vol1h, compare
      with the reference score minus the vol1h weights. Expected working-zone medians BTC 13.3k, ETH 9.9k, SOL 10.8k.
      Done by the review thread 2026-10-27 15:4x (code 9ac61c2): `_weighted_vote_compute` with the v8 config on Engine operand values
      equals the v8 masks on every bar of BTC/ETH/SOL, long and short, 0 differences (`review/live/vote_review/engine_vote_check.py`).
