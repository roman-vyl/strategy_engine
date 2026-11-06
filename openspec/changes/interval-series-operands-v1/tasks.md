## 1. Contracts and arithmetic

- [x] 1.1 Add scale and denominator_mode parsing with strict fields/types; retain omitted/positive ratio identities and legacy floor behavior.
- [x] 1.2 Test negative denominators, exact ±floor boundaries, zero, missing inputs and nonfinite values; verify old default-ratio results remain unchanged.
- [x] 1.3 Define interval_change AST and bounded sampled-series validation; reject nested episode-dependent sampled expressions and non-base features.

## 2. Intervals and endpoint measurements

- [x] 2.1 Implement fixed interval resolution without an episode dependency; test N differences versus N+1 samples and insufficient history.
- [x] 2.2 Resolve impulse/pullback and optional last_n from the existing current-touch projection for both sides; test degenerate legs and no hindsight endpoints.
- [x] 2.3 Implement four endpoint operations and composition over arithmetic series, with finite masks, explicit scale and outer signed direction.
- [x] 2.4 Add independent numeric examples distinguishing fixed from clipped windows and normalized-gap change from difference of EMA slopes.

## 3. Engine integration

- [x] 3.1 Integrate recursion into static semantics, feature requests, episode dependencies and weighted-vote operand acceptance; test rejection before data acquisition.
- [x] 3.2 Extend live history planning for endpoint warm-up and historical impulse endpoints; test full-history versus warmed-prefix values and NaN masks.
- [x] 3.3 Add node identities and shared dependency accounting; test multiple inputs sharing a series with different intervals/thresholds and independent versus batch evaluation.
- [x] 3.4 Preserve old window_change and ratio numeric behavior, node identities and existing strategy outputs; extend operand diagnostics without changing response envelopes.

## 4. Reference acceptance

- [x] 4.1 Create a formula-to-operand mapping for affected NVS3 fixed-window, impulse, normalized-gap and signed-ratio cases; record eligibility, sign, units, denominator floor and entry-candle inclusion. Exclude every SPOT-dependent expression.
- [x] 4.2 Build deterministic fixtures with independent reference formulas; do not use Engine outputs as reference. Test long/short, zero and negative denominators, NaN endpoints, short/long legs and time-prefix causality.
- [x] 4.3 Compare supported affected formulas against frozen BTC/ETH/SOL research arrays on identical entry bars and episode points. Save fixture/source hashes, finite-mask differences, max absolute/relative errors and offending entries; investigate any mismatch rather than recalibrate.
- [x] 4.4 Feed matched values through existing frozen curves and exponent weights, compare individual weights and block masks without changing coefficients or thresholds. Distinguish operand parity from full-system parity; do not claim full NVS3 while SPOT inputs are excluded.

## 5. Documentation and checks

- [x] 5.1 Add runnable example specs for fixed EMA slope, normalized-gap velocity and impulse slope ratio, containing all constants in configuration.
- [x] 5.2 Update public schema/catalog and canonical predicate documentation; document explicit scaling and the difference between fixed and episode-clipped intervals.
- [x] 5.3 Run affected parser/evaluation/planning/vote/history/identity tests, lint/type checks and strict OpenSpec validation. Record results and any independent baseline failures.
- [x] 5.4 Deliver implementation and parity report for review; do not deploy containers, publish manifests or change frozen research artifacts as part of this change.
