## 0. Baseline

- [ ] 0.1 Confirm the invariants this change keeps for specs without the new kinds, operands or range fields: the existing
      memo compute-count, node-identity, plan-label, predicate and composite suites pass unchanged on `main` and after every
      group. Verify: suite run before group 1 and after each group.

## 1. MACD feature kinds

- [ ] 1.1 `indicators/implementations/macd.py`: validator (`source = close`, exactly `fast`, `slow`, `signal`, strict positive
      integers, `fast < slow`, no dependencies) and `compute_macd(close, fast, slow, signal) -> (macd, signal, hist)` with
      `ewm(span, adjust=False)`. Verify: tests against an independent pandas formula to 1e-12; every rejection.
- [ ] 1.2 `feature_kinds.py`: contract entries `macd`, `macd_signal`, `macd_hist` (schema, label
      `<kind>_close_<tf>_<fast>_<slow>_<signal>`, identity params). `range_evaluator.py`: math branch with one cache per
      `(timeframe, fast, slow, signal)`. Verify: one computation for three kinds; labels and identities; 1h completed-bar
      visibility; public catalog, schema and range evaluation API; readiness list in `health.py`.
- [ ] 1.3 `indicator_requirements.py`: MACD warm-up = EMA convergence bars of `slow` + of `signal`. Verify: planner test.
- [ ] 1.4 MACD usable as a predicate feature operand with no predicate-layer change. Verify: `compare` over `macd_hist` test.

## 2. Range extension

- [ ] 2.1 Parse `min`/`max` as number or `null`, `bounds` (`inclusive` default | `exclusive`), `empty` (`block` default |
      `pass`); validation of `min ≤ max` / `min < max`; `short` override may replace `min`, `max`, `bounds`, `empty`.
      Verify: acceptance and rejection tests.
- [ ] 2.2 Evaluation with `null` sides, both bound modes and both empty policies. Verify: tests, including both `null`.
- [ ] 2.3 Identity: `bounds` and `empty` in params only when not default. Verify: every existing range config keeps its mask
      and identity (test pinned against the pre-change identity).

## 3. Segment and ratio operands

- [ ] 3.1 Parse `segment` (all fields required, allowed pairs, `select`, `aggregate`, unknown fields rejected, declared
      episode) and `ratio` (no nested ratio, not both constants); allow them in `compare` and `range`, reject them in
      `change`; `short` override never introduces them. `Predicate.features()` includes segment series.
      Verify: static validation tests.
- [ ] 3.2 Segment evaluation on the side's episode: points from the current touch row, inclusive ends, side sign, three
      selections, `sum` / `mean_per_bar` by prefix sums, `max` by sparse table, missing on no touch / non-finite inside /
      non-base timeframe (fail closed). Verify: long and short, every `select` × `aggregate` against a brute-force loop,
      empty and NaN cases, bar `P` in both legs.
- [ ] 3.3 Ratio evaluation, missing on a missing side or `right ≤ 0`. Verify: zero and negative denominator tests.
- [ ] 3.4 Identity twins `predicate.segment` and `predicate.ratio`, nested consumption order in `PredicateIdentity.nested`,
      memo pre-pass. Verify: memo on = memo off, zero `unforeseen_consumptions`, band candidates differing only in bounds
      share MACD columns, segments and ratio in one batch.
- [ ] 3.5 `composites_need_context_bundle` detects segments inside a ratio or a temporal predicate. Verify: test.
- [ ] 3.6 Live history: zero-additional entry for predicates over segment or ratio. Verify: planner test.

## 4. Evidence

- [ ] 4.1 `composite_setup` trace `child:<child_id>:value` for a range over a segment or ratio; nothing new for other
      children. Verify: trace test and unchanged trace for an existing composite.

## 5. A1 end to end (fixture)

- [ ] 5.1 A1 as one `composite_setup` child on a synthetic market with an EMA-stack episode: value equals a reference loop
      written like research (`S*..P`, `P..t`), band masks for `(low, null)`, `(low, high)`, `(null, null)`.
      Verify: test.

## 6. Acceptance on the owner's data (Mac stack, separate session)

- [ ] 6.1 A1 per EMA500 entry equals `a1_engine_ref_btc.csv.gz` (2185) and `a1_engine_ref_eth.csv.gz` (1970) to 1e-9; `S*`
      and `P` match.
- [ ] 6.2 Block masks: ETH `(0.32, null)` → 459, BTC `(0.44, 3.5)` → 737, `(null, null)` → 0.
- [ ] 6.3 One Engine run of ETH EMA500, W9, lookback 140, SL 8, TP 6.5, band `(0.32, null)` equals the replay on net, trades
      and win rate.

## 7. Gate

- [ ] 7.1 ruff, mypy, the full suite without `tests/parity`.
- [ ] 7.2 `openspec validate a1-band-filter-v1 --strict`.
