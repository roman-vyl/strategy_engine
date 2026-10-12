## 0. Baseline and reference

- [ ] 0.1 Branch after B1/B2 (PR #33) is merged. A1/A2/B1/B2 suites pass unchanged after every group. Verify: suite run.
- [ ] 0.2 D6 answered by the research thread (`c1/c1_values.py`): previous pullback end, floor, `C[P]`, inclusive `t`. The reference rows carry the intermediate values (counter DI at `P`, max and mean of each wave, rise and area of both waves); a bar offset found at parity is reported.

## 1. Parse and validate

- [ ] 1.1 `to: touch` only with `touch: previous` and `from: peak`; rejected with `touch: current`, `from: origin` or `peak → current` previous. Verify: acceptance and rejection tests.
- [ ] 1.2 `by_side` with `di_minus` for long and `di_plus` for short accepted (B2 parser). Verify: test.
- [ ] 1.3 Identity: `to: touch` enters the segment identity; B2, A1 and A2 identities unchanged. Verify: identity test.

## 2. Evaluation

- [ ] 2.1 `peak → touch` previous: first touch (missing), second and later touches, a new episode (the previous touch of another episode is never read). Verify: brute-force loop.
- [ ] 2.2 C1.1 and C1.2 as `range(ratio(segment, segment, right_floor 1e-6))` against a research-style loop: previous value ≤ 1e-6 passes, numerator ≤ 0 is a value, `(null, null)` passes everything, both tails cut. Verify: tests.
- [ ] 2.3 End to end on the BTC fixture for both variants and for period 14 and another period (values to 1e-9, band masks). Verify: test.
- [ ] 2.4 Only bars ≤ t are read (changing later bars leaves earlier values unchanged). Verify: truncation test.
- [ ] 2.5 Short side reads `di_plus`. Verify: test.

## 3. Identity, sharing, cost

- [ ] 3.1 Candidates that differ only in a bound share both segments and the ratio; C1.1 and C1.2 share the `di` columns; `unforeseen_consumptions` stays 0; memo and plain evaluation agree. Verify: batch tests.
- [ ] 3.2 A spec without the touch end point has an identical node set and results. Verify: A1/A2/B1/B2 suites and parity corpus unchanged.
- [ ] 3.3 Cost: benchmark on the A1 band fixture and a long synthetic series. Verify: table in the report.

## 4. Parity with the research reference (owner's Mac, separate session, after the owner's word)

- [ ] 4.0 DI check: the counter DI at `P` of both waves against the reference (as B2 4.0).
- [ ] 4.1 Values: the reference export of every entry, C1.1 and C1.2, to 1e-9, NaN equal; `P`/`T` of both waves and the intermediate values equal.
- [ ] 4.2 Blocked-entry counts at several thresholds per variant, BTC and ETH.
- [ ] 4.3 Replay cells to the cent on a local Engine from the branch. BTC W7 / LB 20 / SL 7 / TP 5.5: no filter 427 trades / $25,760.99; the C1.1 and C1.2 cells from the reference files; one run with all bounds null equals no filter. At most 200 Engine runs in total.
- [ ] 4.4 Situations: first touch (missing, passes), previous rise ≤ 1e-6, one-bar pullback, DI warm-up, short mirror, no look-ahead.
- [ ] 4.5 Backward compatibility: A1, A2, B1 and B2 responses unchanged.
- [ ] 4.6 Report: parity table, wire format; stop for the owner's review.

## 5. Gate

- [ ] 5.1 ruff, mypy, the suite without `tests/parity`.
- [ ] 5.2 `openspec validate c1-di-pullback-wave-v1 --strict`.
