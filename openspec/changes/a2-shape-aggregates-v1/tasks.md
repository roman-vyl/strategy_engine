## 0. Baseline

- [ ] 0.1 Branch from main bb9f0bc. Existing A1 segment, ratio and range suites pass unchanged after every group. Verify: suite run.

## 1. Parse and validate

- [ ] 1.1 `value: change_over` with `span`; `max`, `min`, `abs_sum`, `top_abs_sum` (`top`, `last_n` required); allowed
      (value, aggregate) pairs; unknown fields rejected. Verify: acceptance and rejection tests.
- [ ] 1.2 `eligibility` object (`legs_min_bars`, `window`, `impulse_positive`; `impulse_positive` requires `window`), unknown keys rejected. Verify: tests.

## 2. Evaluation

- [ ] 2.1 `change_over`, `max`, `min` on the episode legs, long and short, windows shorter and longer than leg and span.
      Verify: brute-force loop.
- [ ] 2.2 `abs_sum`, `top_abs_sum`: ties, fewer than `top` bars (sum of all, A2.3 = 1), NaN inside the window. Verify: brute-force loop.
- [ ] 2.3 Eligibility: legs of 1–3 bars counted on the whole leg before the window, a non-finite change in either 75-bar window making all branches missing, impulse sum 0 or negative, later touches, inactive and censored episodes. Verify: tests.
- [ ] 2.3a Division: a numerator ≤ 0 gives a value ≤ 0, not missing (A2.1, A2.2); a denominator ≤ 0 gives missing. Verify: tests.
- [ ] 2.4 A2.1, A2.2, A2.3 as `range(ratio(...))` end to end on the BTC fixture against a research-style reference loop,
      including band masks for `(low, null)`, `(null, high)`, `(low, high)`, `(null, null)`. Verify: test.
- [ ] 2.5 Anchor as a parameter: the same checks with a different anchor period. Verify: unit test.

## 3. Identity, memo, cost

- [ ] 3.1 Identity includes `span`, `top`, `eligibility` only when set; A1 identities unchanged; zero `unforeseen_consumptions`;
      memo on = memo off; band candidates share segments and ratio. Verify: tests.
- [ ] 3.2 Live history: a predicate over a `change_over` or eligibility segment still contributes the zero-additional entry. Verify: planner test.
- [ ] 3.3 Cost: benchmark on the A1 band fixture for each new aggregate; specs without new fields show no slowdown.
      Verify: benchmark table in the report.

## 4. Parity with the research reference (owner's Mac, separate session, after the owner's word)

- [ ] 4.0 Before the comparison: confirm that the csv export equals `a2_ideas_{coin}.npz` (the csv generator is not in the treatise directory) and that the research leg windows (`MT.window`) are inclusive at both ends.
- [ ] 4.1 Coins: BTC 2185 and ETH 1970 EMA500 entries, per branch: values to 1e-9, NaN equal, `S*` and `P` equal.
- [ ] 4.2 Both sides checked separately; every situation label in the export (short legs, NaN and zero cases, ties, later
      touches, thresholds exactly at a bound); situations without a real entry through synthetic series from the same
      reference code.
- [ ] 4.3 Block counts per branch at several thresholds per side on both coins; bound mode reproduces the research counts.
- [ ] 4.4 Full runs by a standard research-service batch run against the deployed Engine, to the cent: BTC A2.1 ≥ 2.5,
      ETH A2.2 ≤ 0.5, ETH A2.3 ≥ 0.35, and one run with all bounds null equal to the run with no filter.
- [ ] 4.5 Backward compatibility: A1 configs and existing range and segment configs identical.
- [ ] 4.6 Report: parity table case × branch (rows compared, max |diff|, NaN mismatches, block-count diffs, full-run diffs),
      wire format of the new fields; stop for the owner's review.

## 5. Gate

- [ ] 5.1 ruff, mypy, the full suite without `tests/parity`.
- [ ] 5.2 `openspec validate a2-shape-aggregates-v1 --strict`.
