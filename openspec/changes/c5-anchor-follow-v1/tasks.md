## 0. Baseline

- [ ] 0.1 Branch from main 59bf49d. A1/A2/B1/B2/C1/V1.3 suites pass unchanged after every group. Verify: suite run (no memo test).

## 1. Parse and validate

- [ ] 1.1 `anchor_follow` operand: required `episode`, no other field; undeclared episode rejected. Verify: tests.
- [ ] 1.2 Accepted as the operand of a `range` and of a `compare` and as a side of a `ratio`; rejected as the operand of a `change`. Verify: tests.
- [ ] 1.3 Identity: own node family; all existing identities unchanged. Verify: identity test.

## 2. Evaluation

- [ ] 2.1 Value against a brute-force loop on synthetic data: long, mirrored short, first bar after the peak, several touches, a new episode. Verify: tests.
- [ ] 2.2 `gap ≤ 0` (empty, passes); non-finite input; negative C5; no wave. Verify: tests.
- [ ] 2.3 C5 in `range`: `(null, null)` passes; values exactly on `low` and `high` block (inclusive); both bounds at once. Verify: tests.
- [ ] 2.4 The anchor follows the stack (EMA500 for 200 / 500 / 1000, EMA1000 for 500 / 1000 / 2000). Verify: test.
- [ ] 2.5 Only bars ≤ t are read (changing later bars leaves earlier values). Verify: truncation test.
- [ ] 2.6 Trace: peak price, EMA at P, EMA at b, gap, move and C5. Verify: trace test.
- [ ] 2.7 End to end on the BTC fixture, values to 1e-9, long and short. Verify: test.

## 3. Identity, sharing, cost

- [ ] 3.1 Candidates differing only in a bound share the operand; `unforeseen_consumptions` stays 0. Verify: batch tests.
- [ ] 3.2 A spec without `anchor_follow` has an identical node set and results. Verify: existing suites and parity corpus.

## 4. Parity with the research reference (owner's Mac, after the owner's word)

- [ ] 4.1 Values against `c5_engine_ref_{btc,eth}` on all entries: EMA at P, EMA at b, gap, move and C5 to 1e-9 relative, NaN equal, long and short separately; report the EMA seed difference at P if the Engine seeds from another first bar than `window_from_ms`.
- [ ] 4.2 Block counts at the thresholds of `c5_parity_{btc,eth}.json` (ETH on `window_to_ms` of the json).
- [ ] 4.3 Engine runs on BTC W7 / LB 20 / SL 7 / TP 5.5 and ETH W11 / LB 20 / SL 8 / TP 5.5 with the filters of the parity files, to the cent; all bounds null equals no filter.
- [ ] 4.4 Backward compatibility: A1, A2, B1, B2, C1, V1.3 responses unchanged; the three A2 control cells match to the cent.
- [ ] 4.5 Report: parity table and wire format; stop for the owner's review.

## 5. Gate

- [ ] 5.1 ruff, mypy, affected tests without `tests/parity` memo.
- [ ] 5.2 `openspec validate c5-anchor-follow-v1 --strict`.
