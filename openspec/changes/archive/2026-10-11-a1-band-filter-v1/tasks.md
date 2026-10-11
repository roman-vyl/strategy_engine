## 0. Baseline

- [x] 0.1 Confirm the invariants this change keeps for specs without the new operands or range fields: the existing memo
      compute-count, node-identity, plan-label, predicate and composite suites pass unchanged on `main` and after every
      group. Verify: suite run before group 1 and after each group.

## 1. Range extension

- [x] 1.1 Parse `min`/`max` as number or `null`, `bounds` (`inclusive` default | `exclusive`), `empty` (`block` default |
      `pass`); validation of `min ≤ max` / `min < max`; `short` override may replace `min`, `max`, `bounds`, `empty`.
      Verify: acceptance and rejection tests.
- [x] 1.2 Evaluation with `null` sides, both bound modes and both empty policies. Verify: tests, including both `null`.
- [x] 1.3 Identity: `bounds` and `empty` in params only when not default. Verify: every existing range config keeps its mask
      and identity (test pinned against the pre-change identity).

## 2. Segment and ratio operands

- [x] 2.1 Parse `segment` (required `episode`, `of`, `from`, `to`, `aggregate`; optional `value`, `window`, `negate`;
      `of` = feature or `difference` of two features; allowed pairs; unknown fields rejected; declared episode) and `ratio`
      (no nested ratio, not both constants); allow them in `compare` and `range`, reject them in `change`; `short` override
      never introduces them. `Predicate.features()` includes the segment series. Verify: static validation tests.
- [x] 2.2 Segment evaluation on the side's episode: points from the current touch row, inclusive ends, side sign, `level` and
      `change`, `last_n` and whole leg, `sum` / `mean_per_bar` / `negate` by prefix sums (telescoping for `change`), missing
      on no touch / non-finite used / non-base timeframe (fail closed). Verify: long and short, every `value` × `window` ×
      `aggregate` against a brute-force loop, `last_n` longer and shorter than the leg, empty and NaN cases, bar `P` in both
      legs, the EMA-difference series.
- [x] 2.3 Ratio evaluation, missing on a missing side or `right ≤ 0`. Verify: zero and negative denominator tests, impulse
      mean ≤ 0.
- [x] 2.4 Identity twins `predicate.segment` and `predicate.ratio`, nested consumption order in `PredicateIdentity.nested`,
      memo pre-pass. Verify: memo on = memo off, zero `unforeseen_consumptions`, band candidates differing only in bounds
      share EMA columns, segments and ratio in one batch.
- [x] 2.5 `composites_need_context_bundle` detects segments inside a ratio or a temporal predicate. Verify: test.
- [x] 2.6 Live history: zero-additional entry for predicates over segment or ratio. Verify: planner test.

## 3. Evidence

- [x] 3.1 `composite_setup` trace `child:<child_id>:value` for a range over a segment or ratio; nothing new for other
      children. Verify: trace test and unchanged trace for an existing composite.

## 4. A1 end to end (fixture)

- [x] 4.1 A1 as one `composite_setup` child on a synthetic market with an EMA-stack episode: value equals a reference loop
      written like research (`d`, `Δ`, last 75 bars of `S*..P` and `P..t`), band masks for `(low, null)`, `(low, high)`,
      `(null, null)`. Verify: test.

## 5. Acceptance on the owner's data (Mac stack, separate session)

- [x] 5.1 A1 per EMA500 entry equals `a1s_engine_ref_btc.csv.gz` (2185 entries, 2016 with a value) and
      `a1s_engine_ref_eth.csv.gz` (1970, 1811) to 1e-9; `S*` and `P` match; NaN equals NaN.
- [x] 5.2 Block counts: BTC `(0.9, null)` 1079, `(0.9, 10)` 1179, `(null, 10)` 100; ETH `(1.2, null)` 1114;
      `(null, null)` 0.
- [x] 5.3 One Engine run of BTC EMA500, W7, lookback 130, SL 7, TP 5.5, band `(0.9, 10)` equals the replay: 205 trades, win
      rate 23.41%, net $37,498.35.

## 6. Gate

- [x] 6.1 ruff, mypy, the full suite without `tests/parity`.
- [x] 6.2 `openspec validate a1-band-filter-v1 --strict`.
