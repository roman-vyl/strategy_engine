## 0. Baseline

- [x] 0.1 Branch from main 59bf49d. A1/A2/B1/B2/C1/V1.3 suites pass unchanged after every group. Verify: suite run (no memo test).

## 1. Parse and validate

- [x] 1.1 `anchor_follow` operand: required `episode`, no other field; undeclared episode rejected. Verify: tests.
- [x] 1.2 Accepted as the operand of a `range` and of a `compare` and as a side of a `ratio`; rejected as the operand of a `change`. Verify: tests.
- [x] 1.3 Identity: own node family; all existing identities unchanged. Verify: identity test.

## 2. Evaluation

- [x] 2.1 Value against a brute-force loop on synthetic data: long, mirrored short, first bar after the peak, several touches, a new episode. Verify: tests.
- [x] 2.2 `gap ≤ 0` (empty, passes); non-finite input; negative C5; no wave. Verify: tests.
- [x] 2.3 C5 in `range`: `(null, null)` passes; values exactly on `low` and `high` block (inclusive); both bounds at once. Verify: tests.
- [x] 2.4 The anchor follows the stack (EMA500 for 200 / 500 / 1000, EMA1000 for 500 / 1000 / 2000). Verify: test.
- [x] 2.5 Only bars ≤ t are read (changing later bars leaves earlier values). Verify: truncation test.
- [x] 2.6 Trace: peak price, EMA at P, EMA at b, gap, move and C5. Verify: trace test.
- [x] 2.7 End to end on the BTC fixture, values to 1e-9, long and short. Verify: test.

## 3. Identity, sharing, cost

- [x] 3.1 Candidates differing only in a bound share the operand; `unforeseen_consumptions` stays 0. Verify: batch tests.
- [x] 3.2 A spec without `anchor_follow` has an identical node set and results. Verify: existing suites and parity corpus.

## 4. Parity with the research reference (owner's Mac, after the owner's word)

- [x] 4.1 Values against `c5_engine_ref_{btc,eth}` on all entries: EMA at P, EMA at b, gap, move and C5 to 1e-9 relative, NaN equal, long and short separately; report the EMA seed difference at P if the Engine seeds from another first bar than `window_from_ms`.
      Mac 2026-10-13, local Engine from 9a922c5: P 0 mismatches. Values BTC 2168 / ETH 1953, empties equal, negatives 3 / 2 equal, max difference 5e-13 (EMA, gap, move and C5; the anchor series agrees with the research EMA).
- [x] 4.2 Block counts at the thresholds of `c5_parity_{btc,eth}.json` (ETH on `window_to_ms` of the json).
      All equal. BTC ≤ 0.017 / 0.024: 87 / 132; ≥ 0.47 / 0.55: 89 / 44. ETH ≤ 0.019 / 0.04: 77 / 191; ≥ 0.51 / 0.55: 39 / 21.
- [x] 4.3 Engine runs on BTC W7 / LB 20 / SL 7 / TP 5.5 and ETH W11 / LB 20 / SL 8 / TP 5.5 with the filters of the parity files, to the cent; all bounds null equals no filter.
      To the cent. BTC W7 / LB 20 / SL 7 / TP 5.5: none 427 / $25,760.99; ≥ 0.55 412 / $34,357.84; ≥ 0.47 406 / $27,180.70; ≤ 0.017 426 / $27,318.67. ETH W11 / LB 20 / SL 8 / TP 5.5: none 176 / $11,200.96; ≥ 0.51 169 / $12,820.78; ≤ 0.04 173 / $12,304.94. All bounds null equals no filter.
- [x] 4.4 Backward compatibility: A1, A2, B1, B2, C1, V1.3 responses unchanged; the three A2 control cells match to the cent.
      The three A2 control cells match to the cent on the branch Engine.
- [x] 4.5 Report: parity table and wire format; stop for the owner's review.
      Parity table above; wire format: `range({"anchor_follow": {"episode": <ref>}})`, `bounds exclusive`, `empty pass`, `min`/`max` = thresholds.

## 5. Gate

- [x] 5.1 ruff, mypy, affected tests without `tests/parity` memo.
- [x] 5.2 `openspec validate c5-anchor-follow-v1 --strict`.
