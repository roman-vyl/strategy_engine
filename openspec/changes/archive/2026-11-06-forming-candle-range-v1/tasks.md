## 1. Operand contract

- [x] 1.1 Extend parser/model with body|range; test invalid values, legacy equivalence, identities and round-trip serialization.
- [x] 1.2 Integrate dependency discovery, memoization, evidence and predicate/vote evaluation.

## 2. Causal calculation

- [x] 2.1 Implement running high/low including the evaluation candle, bucket completeness and missing-data handling.
- [x] 2.2 Reuse existing Wilder ATR with explicit preceding-bucket selection; preserve legacy body alignment.
- [x] 2.3 Update history planning for complete bucket prefix plus ATR warmup; verify warmed-prefix parity.

## 3. Verification and documentation

- [x] 3.1 Test long/short equality, zero range, invalid ATR, missing data, first/last bars, rollover and future-mutation invariance.
- [x] 3.2 Reproduce case 178 on BTC/ETH/SOL against frozen audit inputs; save hashes, missing-mask counts and numeric differences (rtol 1e-7, atol 1e-9).
- [x] 3.3 Add a runnable manifest example and document range semantics and previous-bucket ATR.
- [x] 3.4 Run affected legacy body, HTF, history-planning and weighted-vote regressions, lint/type checks and strict OpenSpec validation; record results.
