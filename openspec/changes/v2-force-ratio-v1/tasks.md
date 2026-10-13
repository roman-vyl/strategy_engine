## 0. Baseline

- [ ] 0.1 Branch from main 59bf49d. A1/A2/B1/B2/C1/V1.3 suites pass unchanged after every group. Verify: suite run (no memo test).

## 1. Parse and validate

- [ ] 1.1 `leg_mean.field` accepts `volume`, `force_with`, `force_against`; anything else rejected; no new keys. Verify: tests.
- [ ] 1.2 Accepted and rejected places of the operand are unchanged (ratio side, range, compare; not change). Verify: tests.
- [ ] 1.3 Identity: node family and params unchanged; V1.3, B1, B2, C1, A1, A2 identities unchanged. Verify: identity test.

## 2. Evaluation

- [ ] 2.1 Derived series against a brute-force loop on synthetic data: long and short sign, bar 0 missing, first impulse bar reads `close[S*−1]`, non-finite close or volume makes the leg missing. Verify: tests.
- [ ] 2.2 Legs: pullback starts at `P+1`, `t = P` missing, one-bar legs, several touches, a new episode. Verify: tests.
- [ ] 2.3 V2.2 in `range`: `(null, null)` passes; missing passes; `imp ≤ 0` passes; negative `pb` is a value; values exactly on `low` and `high` block (inclusive); both bounds at once. Verify: tests.
- [ ] 2.4 Only bars ≤ t are read (changing later bars leaves earlier values). Verify: truncation test.
- [ ] 2.5 End to end on the BTC fixture, values to 1e-9, band masks, long and short separately. Verify: test.

## 3. Identity, sharing, cost

- [ ] 3.1 Candidates differing only in a bound share both operands and the ratio; `unforeseen_consumptions` stays 0. Verify: batch tests.
- [ ] 3.2 A spec without a force field has an identical node set and results. Verify: existing suites and parity corpus.

## 4. Parity with the research reference (owner's Mac, after the owner's word)

- [ ] 4.1 Values against `v2_engine_ref_{btc,eth}` on all entries (1e-9 relative, NaN equal, long and short separately); the two reference points of D4 and D5 reported.
- [ ] 4.2 Block counts at the research thresholds from `v2_parity_{btc,eth}.json`.
- [ ] 4.3 Engine runs: BTC W7 / LB 20 / SL 7 / TP 5.5 and ETH W11 / LB 20 / SL 8 / TP 5.5, with and without V2.2 ≥ 10, to the cent (numbers from the Mac).
- [ ] 4.4 Backward compatibility: A1, A2, B1, B2, C1, V1.3 responses unchanged; the three A2 control cells match to the cent.
- [ ] 4.5 Report: parity table and wire format; stop for the owner's review.

## 5. Gate

- [ ] 5.1 ruff, mypy, affected tests without `tests/parity` memo.
- [ ] 5.2 `openspec validate v2-force-ratio-v1 --strict`.
