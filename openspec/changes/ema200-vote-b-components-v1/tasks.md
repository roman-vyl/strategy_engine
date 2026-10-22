## 0. Baseline

- [ ] 0.1 Branch from main 95162fd. Existing suites (A1, A2, B1, B2, C1, C5, V1.3, V2.2, weighted vote) pass unchanged after every group. Verify: targeted suite run, never `tests/parity/test_all_families_memo.py`.

One filter = one commit: groups 1 to 4 land as one commit per filter, in the order below.

## 1. `wave_measure` operand

- [ ] 1.1 Parse and validate: required `episode`, `measure`; `touch` only with `depth_share`; `atr` required by `impulse_atr` (kind `atr` or `atr_wilder`, base timeframe) and rejected elsewhere; unknown fields rejected; accepted in `ratio`, `range`, `compare`, vote inputs; rejected in `change`. Own node family. Verify: tests.
- [ ] 1.2 B3 `impulse_atr`: brute-force loop on synthetic series; ATR read at P; H ≤ 0 and ATR ≤ 0 missing; short mirror. Commit "B3".
- [ ] 1.3 A3 `speed_ratio`: pullback counts P (`t − P + 1`); t = P gives `|peak − close[P]| ÷ 1`; short mirror. Commit "A3".
- [ ] 1.4 A4 `duration_ratio`: values on one-bar legs; missing when H ≤ 0. Commit "A4".
- [ ] 1.5 A5 `efficiency_gap`: t = P missing; flat path missing; brute-force ER. Commit "A5".
- [ ] 1.6 C3.1 `depth_share` current: extreme over `P..t` including P; a new low after the entry bar is not read. Commit "C3.1".
- [ ] 1.7 C3.2 `depth_share` previous and `ratio` with `right_floor`: first touch missing; extreme over `P0..S*` inclusive; previous depth ≤ floor missing; a touch of an earlier episode never read. Commit "C3.2".

## 2. `leg_volume` operand

- [ ] 2.1 Parse and validate: `leg`, `aggregate`, `bars`, `top_share` in (0, 1] only with `top_mean`, `top_mean` with `own_color` rejected. Own node family. Verify: tests.
- [ ] 2.2 V1.1 `sum`: legs `[S*, P]` and `[P+1, t]`; t = P missing; zero impulse sum makes the ratio missing. Commit "V1.1".
- [ ] 2.3 V1.2 `own_color`: doji excluded; pullback colour is the opposite one; short mirror. Commit "V1.2".
- [ ] 2.4 V1.4 `top_mean`: `k = max(1, ceil(top_share · L))` in float64 (L = 30, share 0.1 → k = 4); impulse once per touch; truncation test. Commit "V1.4".

## 3. `forming_candle` operand

- [ ] 3.1 D1: UTC day buckets; open of the first existing bar of the bucket; ATR of the previous closed day (`atr_wilder` 14, 1d); missing without ATR; with `episode` missing where there is no valid wave; next bar takes the new close; short mirror. Commit "D1".

## 4. Identity, sharing, cost

- [ ] 4.1 Candidates that differ only in a level or a bound share every new operand; `unforeseen_consumptions` stays 0. Verify: batch tests.
- [ ] 4.2 A spec without the new operands has an identical node set and identical results. Verify: existing suites.
- [ ] 4.3 Timing of a vote B spec on a full BTC 5m history in one batch, reported (top_mean included).

## 5. Vote B config

- [ ] 5.1 A test spec with the vote B table of design D6 parses, validates and evaluates; block on the D1 step alone, on V1.1 + A5, on any veto; no block at 0.7382 (A2.2 + A5).

## 6. Parity with research on EMA200 (cloud, after the owner's word)

- [ ] 6.1 Reference tables built in the cloud from `/mnt/project-files/ema200_calib/` (candles npz, entries, `alt_*.npz` / research values) for BTC, ETH, SOL: every entry with a wave, values of D1, V1.1, V1.2, V1.4, C3.1, C3.2, A3, B3, A5, A4. The existing A1s, A2.2, B1 15m, V1.3, V2.2, C5 already match on EMA200 (main 95162fd, 1e-9, `/mnt/project-files/engine-tasks/ema200/parity/README.md`); reuse its `run_engine.py` / `compare.py` and `ema_stack_episode.window_bars` 24 for EMA200. Target 1e-9 relative, NaN equal; differences explained (filled grid, first ATR day).
- [ ] 6.2 Vote B block masks equal to research on all entries of the working zones (BTC 447, ETH 372, SOL 218 unique entries).
- [ ] 6.3 Report the parity table; stop for the owner's review.

## 7. Gate

- [ ] 7.1 ruff, mypy, affected tests without `tests/parity` memo.
- [ ] 7.2 `openspec validate ema200-vote-b-components-v1 --strict`.
