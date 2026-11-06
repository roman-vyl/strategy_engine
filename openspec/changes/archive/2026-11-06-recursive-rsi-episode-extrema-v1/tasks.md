## 1. Reference and regression fixtures

- [x] 1.1 Verify original altvals C6 formula and frozen HIST:c6r arrays; record source hashes, candle origin, base timeframe and entry/point alignment for BTC/ETH/SOL.
- [x] 1.2 Add synthetic fixtures for zero seed, flat/one-sided/mixed prices, invalid prices, previous-wave mapping, entry=P and extreme occurring on entry.
- [x] 1.3 Freeze legacy rsi/segment values and identities to detect accidental changes.

## 2. Generic recursive RSI feature

- [x] 2.1 Implement and register rsi_ewm with period validation and exact zero-seeded recurrence; expose through catalog/schema and ordinary feature evaluation.
- [x] 2.2 Integrate feature identity, history planning, prefix-origin metadata and completed-HTF visibility; document exact-prefix versus warm-up convergence semantics.
- [x] 2.3 Test numerical parity, missing masks, period1, strict validation, append-future invariance and unchanged legacy rsi behavior.

## 3. Existing segment extension

- [x] 3.1 Extend AST/parser/schema with level min/max, include_start and empty_policy; validate supported combinations and preserve default legacy identities.
- [x] 3.2 Implement causal boundary selection and finite-sample extrema using existing current/previous episode mapping and range-extreme utility.
- [x] 3.3 Test current/previous intervals, strict previous ordering, peak exclusion, entry inclusion, coincident fallback, last_n order, missing interior samples, unavailable history and future endpoints.
- [x] 3.4 Test recursive feature collection, arithmetic composition and cache separation for nondefault boundary options.

## 4. C6 composition and acceptance

- [x] 4.1 Add a valid strategy/manifest example for both sides using rsi_ewm168 and generic segment differences; verify normal parse/plan/evaluation paths without C6-specific dispatch.
- [x] 4.2 Add a reproducible parity tool with configurable reference paths; calculate RSI on identical full input prefixes before slicing, verify point alignment, and compare all available original C6 entries plus study-selected entries on all three coins.
- [x] 4.3 Save per-coin/direction counts, finite max errors, missing mismatches, seed origins, input hashes and representative edge cases; require <=1e-9 finite error and zero unexplained missing mismatches.
- [x] 4.4 Run affected indicator/API/parser/evaluator/history/identity tests and required repository checks; record commands/results in acceptance report.
- [x] 4.5 Document new generic components, limits and opt-in migration; leave strategy deployment, voting settings and manual ratings unchanged.
