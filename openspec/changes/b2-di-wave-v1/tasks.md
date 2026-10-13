## 0. Baseline and reference

- [x] 0.1 Branch from main (e00defc or a newer main). A1/A2 segment, ratio and range suites pass unchanged after every group. Verify: suite run.
- [x] 0.2 D7 and the DI smoothing question answered (13:58, 14:3x): wave n−1 from the same episode, denominator floor 1e-6, `D[S*]` on bar `S*`, DI over the whole history, existing `di_*` features reused (D4a). The reference rows carry the intermediate values (DI at `S*`, max and mean of each wave, ΔDI and area of both waves); a bar offset found at parity is reported.

## 1. Parse and validate

- [x] 1.1 `touch` field (`current` default, `previous`); `previous` only with `origin → peak`; unknown values rejected. Verify: acceptance and rejection tests.
- [x] 1.2 `of` accepts `by_side` with exactly `long` and `short` feature references; both on the base timeframe. Verify: tests.
- [x] 1.3 `value: from_start` with `sum`, `mean_per_bar`, `max`, `min`; `change`/`change_over` aggregates rejected with it. Verify: tests.
- [x] 1.5 `ratio.right_floor` (finite number, default 0), rejected when not finite; enters the ratio identity only when set. Verify: tests.
- [x] 1.4 Identity: `touch`, `by_side` and `from_start` enter the segment identity only when set; the A1/A2 identities are unchanged. Verify: identity test.

## 2. Evaluation

- [x] 2.1 `touch: previous`: first touch of an episode (missing), second and later touches, a new episode (the previous touch of another episode is never read), inactive and censored episodes. Verify: brute-force loop.
- [x] 2.2 `by_side`: long reads `di_plus`, short reads `di_minus`, no negation on short; plain feature and difference series still negate on short. Verify: tests.
- [x] 2.3 `from_start`: max/min/sum/mean_per_bar against a brute-force loop, window of one bar, non-finite value at the start and inside the window, `window.last_n`. Verify: brute-force loop.
- [x] 2.4 B2.1 and B2.2 as `range(ratio(segment, segment, right_floor 1e-6))`: previous value ≤ 1e-6 (zero, negative, tiny positive) passes, numerator ≤ 0 is a value, `(null, null)` passes everything, a lower bound cuts. Verify: tests.
- [x] 2.5 End to end on the BTC fixture for both variants and for period 14 and another period, against a research-style loop (values to 1e-9, band masks). Verify: test.
- [x] 2.6 Only bars ≤ t are read (changing later bars leaves earlier values unchanged). Verify: truncation test.

## 3. Identity, sharing, cost

- [x] 3.1 Candidates that differ only in `min`/`max` share both segments and the ratio; B2.1 and B2.2 share the `di` columns and the points; `unforeseen_consumptions` stays 0; memo and plain evaluation agree. Verify: batch tests.
- [x] 3.2 A spec without `touch`, `by_side` or `from_start` has an identical node set and results. Verify: A1/A2 suites and parity corpus unchanged.
- [x] 3.3 Cost: benchmark `from_start` max and mean_per_bar, `touch: previous` on the A1 band fixture and a long synthetic series; no dependence on leg length beyond the sparse-table depth. Verify: benchmark table in the report.
- [x] 3.4 Live history: no entry beyond the episode and DI feature requirements. Verify: planner test.

## 4. Parity with the research reference (owner's Mac, separate session, after the owner's word)

- [x] 4.0 DI check first: Engine `di_plus`/`di_minus` (period 14, base timeframe) against the reference DI on the bars `S*` and `P` of every entry; differences are expected to be below 1e-9 after about 320 bars; report any bar offset.
- [x] 4.1 Values: `b2/b2_engine_ref_btc.csv.gz` and `b2/b2_engine_ref_eth.csv.gz`, every entry, B2.1 and B2.2, to 1e-9, NaN equal; S*/P of both waves equal and the intermediate values (DI at `S*`, max, mean, ΔDI, area) equal.
- [x] 4.2 Blocked-entry counts of `b2/b2_parity_btc.json` and `b2/b2_parity_eth.json` at several thresholds per variant.
- [x] 4.3 Replay cells of the two parity files to the cent on a local Engine from the branch. BTC W7 / LB 20 / SL 7 / TP 5.5: no filter 427 trades / $25,760.99;
      B2.1 ≤ 0.7 408 / $36,532.39; B2.2 ≤ 0.8 398 / $38,525.90. ETH W11 / LB 20 / SL 8 / TP 5.5 cells from `b2_parity_eth.json`. One run with all bounds null equals no filter. At most 200 Engine runs in total.
- [x] 4.4 Situations: first touch (missing, passes), ΔDI_{n−1} ≤ 0, DI warm-up, one-bar impulse, short mirror (−DI), no look-ahead.
- [x] 4.5 Backward compatibility: A1 and A2 responses unchanged.
- [x] 4.6 Report: parity table, wire format; stop for the owner's review.

Parity result (Mac, local Engine from main 878a589, owner 2026-10-13):

- Points S*, P, S*(n−1), P(n−1): 0 mismatches. Counter DI at S* of both waves within 5e-11.
- B2.1: BTC 1401 / ETH 1228 values, empties equal, max relative difference 5e-12. B2.2: BTC 1158 / ETH 1060 values, empties equal, max absolute difference 5e-7 (reference exactly 0 against Engine ±1e-11 from prefix sums, and one ETH value 324.13); float noise, no threshold affected.
- Blocked-entry counts equal at all 8 thresholds on both coins (BTC B2.1 ≤ 0.7 286, B2.2 ≤ 0.8 375).
- All cells to the cent, 9 per coin. BTC W7 / LB 20 / SL 7 / TP 5.5: none 427 / $25,760.99, B2.1 ≤ 0.7 408 / $36,532.39, B2.2 ≤ 0.8 398 / $38,525.90. ETH W11 / LB 20 / SL 8: none 176 / $11,200.96, B2.1 ≤ 0.7 166 / $16,043.23, B2.2 ≤ 0.8 158 / $12,847.02. All bounds null equals no filter.
- Situations: first touch 736 / 701 empty and passes; previous rise ≤ 1e-6 31 / 24 and previous area 274 / 192 empty; shorts 612 / 551; one-bar impulse 12 / 5 entries, all match.
- The three A2 control cells match to the cent.

## 5. Gate

- [x] 5.1 ruff, mypy, the suite without `tests/parity`.
- [x] 5.2 `openspec validate b2-di-wave-v1 --strict`.
