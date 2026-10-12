## 0. Baseline

- [x] 0.1 Branch from main a96f37e (B1/B2 merged). A1/A2/B1/B2 suites pass unchanged after every group. Verify: suite run.

## 1. Parse and validate

- [x] 1.1 `leg_mean` operand: required `episode`, `leg`, `field`; unknown fields rejected; `leg` in {impulse, pullback}; `field` = `volume`; undeclared episode rejected. Verify: tests.
- [x] 1.2 Accepted as a side of a `ratio`, as the operand of a `range` and of a `compare`; rejected as the operand of a `change`. Verify: tests.
- [x] 1.3 Identity: own node family; B1/B2/C1/A1/A2 identities unchanged. Verify: identity test.

## 2. Evaluation

- [x] 2.1 Impulse `[S*, P]` and pullback `[P+1, t]` against a brute-force loop on synthetic series: first bar of the pullback, `t = P` (missing), one-bar legs, several touches, a new episode. Verify: tests.
- [x] 2.2 V1.3 in `range`: `(null, null)` passes, missing passes, impulse mean 0 passes, values exactly on `low` and `high` block (inclusive), both bounds at once. Verify: tests.
- [x] 2.3 Only bars ≤ t are read (changing later volume leaves earlier values). Verify: truncation test.
- [x] 2.4 Short side mirrors (the legs are the same; the value is side-independent). Verify: test.
- [x] 2.5 End to end on the BTC fixture, values to 1e-9, band masks. Verify: test.

## 3. Identity, sharing, cost

- [x] 3.1 Candidates that differ only in a bound share both operands and the ratio; `unforeseen_consumptions` stays 0. Verify: batch tests.
- [x] 3.2 A spec without `leg_mean` has an identical node set and results. Verify: existing suites and parity corpus.

## 4. Parity with the research reference (owner's Mac, after the owner's word)

- [x] 4.1 Values against `v1_engine_ref_{btc,eth}` on all entries (1e-9 relative, NaN equal); volume source difference reported.
- [x] 4.2 Block counts at the five thresholds per coin from `v1_parity_*.json`.
- [x] 4.3 Engine runs: BTC and ETH cells to the cent (BTC W7 LB20 SL7 TP5.5 none 427 / $25,760.99, ≤0.23 405 / $28,135.05, ≤0.12 422 / $27,342.82; ETH W11 LB20 SL8 none 176 / $11,200.96, ≤0.26 168 / $15,042.65, ≤0.48 138 / $16,604.07).
- [x] 4.4 Backward compatibility: A1, A2, B1, B2 responses unchanged.
- [x] 4.5 Report: parity table and wire format; stop for the owner's review.

Parity result (Mac, local Engine from 7f6bb77, owner 2026-10-12):

- S* and P: 0 mismatches. V1.3 values: BTC 2168, ETH 1953, empties equal, max relative difference 7e-11. The Engine `volume` and research `volume_value` are the same series (values agree to 1e-10).
- Blocked-entry counts equal at all 5 thresholds per coin.
- Cells to the cent. BTC W7 / LB 20 / SL 7 / TP 5.5: none 427 / $25,760.99; ≤ 0.12 422 / $27,342.82; ≤ 0.19 417 / $26,392.25; ≤ 0.23 405 / $28,135.05; ≥ 2.4 423 / $23,553.56; ≥ 4.9 426 / $27,318.67. ETH W11 / LB 20 / SL 8: none 176 / $11,200.96; ≤ 0.26 168 / $15,042.65; ≤ 0.33 157 / $13,931.56; ≤ 0.48 138 / $16,604.07; ≥ 2.4 175 / $12,061.12; ≥ 4.6 176 / $11,200.96. All bounds null equals no filter.
- The three A2 control cells match to the cent; no threshold is hardcoded in the Engine.

## 5. Gate

- [x] 5.1 ruff, mypy, affected tests without `tests/parity` memo.
- [x] 5.2 `openspec validate v1-volume-ratio-v1 --strict`.
