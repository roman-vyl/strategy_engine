## 0. Baseline

- [x] 0.1 Record the invariants kept for specs without `anchor_stack_width_band_setup`: evaluation outputs, `plan_hash` and plan
      labels, memoized node identities and compute counts per node family. Verify: the existing suites that pin them pass unchanged.

## 1. Static contract

- [x] 1.1 Add `anchor_stack_width_band_setup` to `SETUP_SUPPORTED` and to `SEMANTIC_SETUP_CHILDREN`.
- [x] 1.2 One parsing function for the parameters (D2), shared by validation, compute and resolve. Verify: rejection tests for a
      missing `min_width_atr`, boolean, non-numeric, non-finite and non-positive bounds, `max_width_atr: null`,
      `max_width_atr < min_width_atr`, a non-positive `atr_period`, an unknown key; acceptance with and without `max_width_atr`, with
      `min == max`.
- [x] 1.3 Static validation runs the parsing for top-level setups and for `composite_setup` children, market-data-free. Verify:
      tests at top level, with `context_consumption`, and as a composite child.

## 2. Planning

- [x] 2.1 `plan_setup_columns`: `{fast, slow, atr}` via `add_atr`. Verify: a spec with the band and an old width setup on the same
      ATR plans one ATR feature; a spec without the band has an unchanged plan and `plan_hash`.
- [x] 2.2 Live history: explicit zero-additional-history entry in `_semantic_setup`. Verify: planner tests for a base ATR, a
      higher-timeframe ATR, and a composite child.

## 3. Evaluation

- [x] 3.1 Compute (D3): vectorized width node and band test, trace (D5). Verify: inclusive bounds at exact `min` and `max`, no upper
      bound, readiness, higher-timeframe ATR, identical masks for both sides, determinism.
- [x] 3.2 Width equivalence: `width_atr` equals `current_width_atr` of the existing setup for the same ATR. Verify: test on a real frame.
- [x] 3.3 Composite child: local mask equals the same setup declared directly. Verify: test.

## 4. Identity and memo

- [x] 4.1 Resolve twins for both node families (D8). Verify: bounds-only candidates share one `width` node; `5` and `5.0` give one
      identity; absent `max_width_atr` differs from any present value; zero `unforeseen_consumptions`; memoized and non-memoized
      outputs bit-identical.

## 5. Catalog

- [x] 5.1 One `ComponentSchema` for `anchor_stack_width_band_setup` (role `setup`, params of D2, context consumption as other setups).
      Verify: catalog test.

## 6. Gate

- [x] 6.1 The group 0 regression is green after every group.
- [x] 6.2 ruff, mypy, the full suite (without `tests/parity`) are green.
- [x] 6.3 `openspec validate anchor-stack-width-band-setup-v1 --strict` passes.
