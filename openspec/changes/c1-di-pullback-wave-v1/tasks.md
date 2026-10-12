## 0. Baseline and reference

- [x] 0.1 Branch after B1/B2 (PR #33) is merged. A1/A2/B1/B2 suites pass unchanged after every group. Verify: suite run.
      Mac 2026-10-12 at 532eade: suite without `tests/parity` passes except `test_live_entry_responses_unchanged`, which fails the same way on main a96f37e on this Mac (byte hash, not C1).
- [x] 0.2 D6 answered by the research thread (`c1/c1_values.py`): previous pullback end, floor, `C[P]`, inclusive `t`. The reference rows carry the intermediate values (counter DI at `P`, max and mean of each wave, rise and area of both waves); a bar offset found at parity is reported.
      Reference `c1/c1_values.py` (default PREV=s), `c1s_values_*`, `c1_engine_ref_*`, `c1_parity_*`: wave n = `P … T_n`, wave n−1 = `P_{n−1} … S*_n`, floor 1e-6, `C[P]` on the peak bar. No bar offset.

## 1. Parse and validate

- [x] 1.0 `to: touch` (the touch bar of the current touch row) only with `touch: current`; rejected with `touch: previous`. The current wave is `P … T`, frozen after the touch. Verify: acceptance, rejection and freeze tests.
- [x] 1.1 `to: next_origin` only with `touch: previous` and `from: peak`; rejected with `touch: current`, `from: origin` or `peak → current` previous. Verify: acceptance and rejection tests.
- [x] 1.2 `by_side` with `di_minus` for long and `di_plus` for short accepted (B2 parser). Verify: test.
- [x] 1.3 Identity: `to: next_origin` enters the segment identity; B2, A1 and A2 identities unchanged. Verify: identity test.

## 2. Evaluation

- [x] 2.1 `peak → next_origin` previous: first touch (missing), second and later touches, a degenerate segment (empty), a new episode (the previous touch of another episode is never read). Verify: brute-force loop.
- [x] 2.2 C1.1 and C1.2 as `range(ratio(segment, segment, right_floor 1e-6))` against a research-style loop: previous value ≤ 1e-6 passes, numerator ≤ 0 is a value, `(null, null)` passes everything, both tails cut. Verify: tests.
- [x] 2.3 End to end on the BTC fixture for both variants and for period 14 and another period (values to 1e-9, band masks). Verify: test.
- [x] 2.4 Only bars ≤ t are read (changing later bars leaves earlier values unchanged). Verify: truncation test.
- [x] 2.5 Short side reads `di_plus`. Verify: test.

## 3. Identity, sharing, cost

- [x] 3.1 Candidates that differ only in a bound share both segments and the ratio; C1.1 and C1.2 share the `di` columns; `unforeseen_consumptions` stays 0; memo and plain evaluation agree. Verify: batch tests.
- [x] 3.2 A spec without the next-origin end point has an identical node set and results. Verify: A1/A2/B1/B2 suites and parity corpus unchanged.
- [x] 3.3 Cost: benchmark on the A1 band fixture and a long synthetic series. Verify: table in the report.
      End to end on the full BTC/ETH history (local Engine, two coins in parallel): no filter 12–20 s, one C1 range 16–20 s, all-null C1 16–22 s, within run-to-run noise. No synthetic micro-benchmark was run.

## 4. Parity with the research reference (owner's Mac, separate session, after the owner's word)

- [x] 4.0 DI check: the counter DI at `P` of both waves against the reference (as B2 4.0).
- [x] 4.1 Values: the reference export of every entry, C1.1 and C1.2, to 1e-9, NaN equal; `P`/`T` of both waves and the intermediate values equal.
- [x] 4.2 Blocked-entry counts at several thresholds per variant, BTC and ETH.
- [x] 4.3 Replay cells to the cent on a local Engine from the branch. BTC W7 / LB 20 / SL 7 / TP 5.5: no filter 427 trades / $25,760.99; the C1.1 and C1.2 cells from the reference files; one run with all bounds null equals no filter. At most 200 Engine runs in total.
- [x] 4.4 Situations: first touch (missing, passes), previous rise ≤ 1e-6, one-bar pullback, DI warm-up, short mirror, no look-ahead.
- [x] 4.5 Backward compatibility: A1, A2, B1 and B2 responses unchanged.
- [x] 4.6 Report: parity table, wire format; stop for the owner's review.

Parity result (Mac, local Engine from 532eade, 82 Engine runs in total; owner 2026-10-12: current wave `P … T` to the touch, previous wave `P(n−1) … S*(n)`):

- Points P, T, P(n−1), S*(n): 0 mismatches on 2185 BTC / 1970 ETH entries; counter DI at P of both waves within 5e-11.
- Values against `c1s_values_*`: same entries have a value; C1.1 within 5e-13; C1.2 within 1e-9 relative except 3 BTC / 2 ETH entries (≤ 5e-9, float noise on ratios 8–66).
- Blocked-entry counts equal at all 5 thresholds per coin.
- Cells to the cent. BTC W7 / LB 20 / SL 7 / TP 5.5: none 427 / $25,760.99; C1.1 ≤ 0.36 422 / $27,788.59; ≤ 0.41 421 / $28,100.06; ≤ 0.49 425 / $25,545.03; C1.2 ≥ 2.6 420 / $25,366.36; ≥ 4.3 421 / $27,364.73. ETH W11 / LB 20 / SL 8: none 176 / $11,200.96; C1.1 ≤ 0.36 171 / $10,752.53; ≤ 0.41 170 / $9,544.34; ≤ 0.49 167 / $10,265.88; C1.2 ≥ 2.6 174 / $11,982.49; ≥ 4.3 175 / $11,584.22. All bounds null equals no filter on both coins.
- The three A2 control cells match to the cent; no threshold is hardcoded in the Engine.

## 5. Gate

- [x] 5.1 ruff, mypy, the suite without `tests/parity`.
- [x] 5.2 `openspec validate c1-di-pullback-wave-v1 --strict`.
