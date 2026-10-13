## 0. Baseline

- [x] 0.1 Branch from main 59bf49d. A1/A2/B1/B2/C1/V1.3 suites pass unchanged after every group. Verify: suite run (no memo test).

## 1. Parse and validate

- [x] 1.1 `leg_mean.field` accepts `volume`, `force_with`, `force_against`; anything else rejected; no new keys. Verify: tests.
- [x] 1.2 Accepted and rejected places of the operand are unchanged (ratio side, range, compare; not change). Verify: tests.
- [x] 1.3 Identity: node family and params unchanged; V1.3, B1, B2, C1, A1, A2 identities unchanged. Verify: identity test.

## 2. Evaluation

- [x] 2.1 Derived series against a brute-force loop on synthetic data: long and short sign, bar 0 force 0, first impulse bar reads `close[S*−1]`, non-finite close or volume makes the leg missing. Verify: tests.
- [x] 2.2 Legs: pullback starts at `P+1`, `t = P` missing, one-bar legs, several touches, a new episode. Verify: tests.
- [x] 2.3 V2.2 in `range`: `(null, null)` passes; missing passes; `imp ≤ 0` passes; negative `pb` is a value; values exactly on `low` and `high` block (inclusive); both bounds at once. Verify: tests.
- [x] 2.4 Only bars ≤ t are read (changing later bars leaves earlier values). Verify: truncation test.
- [x] 2.5 End to end on the BTC fixture, values to 1e-9, band masks, long and short separately. Verify: test.

## 3. Identity, sharing, cost

- [x] 3.1 Candidates differing only in a bound share both operands and the ratio; `unforeseen_consumptions` stays 0. Verify: batch tests.
- [x] 3.2 A spec without a force field has an identical node set and results. Verify: existing suites and parity corpus.
- [x] 3.3 Trace carries V2.2 (`child:<id>:value`); signed force sum and bar count of both legs from `mean × leg_bar_counts`. Verify: tests.

## 4. Parity with the research reference (owner's Mac, after the owner's word)

- [x] 4.1 Values against `v2_engine_ref_{btc,eth}` on all entries (1e-9 relative, NaN equal, long and short separately); the two reference points of D4 and D5 reported.
      Mac 2026-10-13, local Engine from 324ba08: S*/P 0 mismatches. Values BTC 1986 / ETH 1816, empties equal (no wave, impulse force ≤ 0), negatives 88 / 71 equal. Max relative difference 5e-10, one BTC entry 3.9e-9 (value 2.8e-5, the pullback force almost cancels: float noise). Known convention difference: research fills a gap candle with force 0, the Engine makes the leg empty; the windows have no gaps.
- [x] 4.2 Block counts at the research thresholds from `v2_parity_{btc,eth}.json`.
      All equal. BTC ≤ 0.007 / 0.027: 123 / 199; ≥ 5 / 8 / 10 / 16: 200 / 139 / 119 / 80. ETH ≤ 0.007 / 0.027: 101 / 165; ≥ 8 / 10 / 16: 112 / 98 / 71.
- [x] 4.3 Engine runs: BTC W7 / LB 20 / SL 7 / TP 5.5 and ETH W11 / LB 20 / SL 8 / TP 5.5, with and without V2.2 ≥ 10, to the cent (numbers from the Mac).
      To the cent. BTC W7 / LB 20 / SL 7 / TP 5.5: none 427 / $25,760.99; ≤ 0.027 407 / $28,775.80; ≥ 5 429 / $28,933.44; ≥ 10 423 / $28,557.57. ETH W11 / LB 20 / SL 8 / TP 5.5: none 176 / $11,200.96; ≤ 0.027 162 / $5,927.51; ≥ 10 173 / $12,527.39. All bounds null equals no filter.
- [x] 4.4 Backward compatibility: A1, A2, B1, B2, C1, V1.3 responses unchanged; the three A2 control cells match to the cent.
      The three A2 control cells match to the cent on the branch Engine.
- [x] 4.5 Report: parity table and wire format; stop for the owner's review.
      Parity table above; wire format: `range(ratio(leg_mean(pullback, force_against), leg_mean(impulse, force_with)))`, `bounds exclusive`, `empty pass`, `min`/`max` = thresholds.

## 5. Gate

- [x] 5.1 ruff, mypy, affected tests without `tests/parity` memo.
- [x] 5.2 `openspec validate v2-force-ratio-v1 --strict`.
